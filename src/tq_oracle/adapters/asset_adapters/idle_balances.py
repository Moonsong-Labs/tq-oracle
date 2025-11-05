from __future__ import annotations

import asyncio
import random

import backoff
from web3 import Web3
from web3.exceptions import ProviderConnectionError

from ...abi import (
    get_oracle_address_from_vault,
    load_erc20_abi,
    load_oracle_abi,
    load_vault_abi,
)
from ...logger import get_logger
from ...settings import OracleSettings
from .base import AdapterChain, AssetData, BaseAssetAdapter

logger = get_logger(__name__)


class IdleBalancesAdapter(BaseAssetAdapter):
    """Adapter for querying Idle Balances assets from L1 or Hyperliquid chain."""

    eth_address: str
    usdc_address: str

    def __init__(self, config: OracleSettings, chain: str = "vault_chain"):
        """Initialize the adapter.

        Args:
            config: Oracle configuration
            chain: Which chain to query - "vault_chain" or "hyperliquid"
        """
        super().__init__(config, chain=chain)

        if chain == "hyperliquid":
            hl_rpc = getattr(config, "hl_rpc", None)
            if not hl_rpc:
                raise RuntimeError(
                    "Hyperliquid RPC is not configured. Re-enable Hyperliquid support before using this adapter."
                )
            self.w3 = Web3(Web3.HTTPProvider(hl_rpc))
            hl_block_number = getattr(config, "hl_block_number", None)
            if hl_block_number is None:
                raise RuntimeError(
                    "Hyperliquid block number is not configured. Re-enable Hyperliquid support before using this adapter."
                )
            self.block_number = hl_block_number
        else:
            self.w3 = Web3(Web3.HTTPProvider(config.vault_rpc_required))
            self.block_number = config.block_number_required

        assets = config.assets
        logger.debug(f"Assets available: {assets}")
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for IdleBalances adapter")
        self.eth_address = eth_address
        usdc_address = assets["USDC"]
        if usdc_address is None:
            raise ValueError("USDC address is required for IdleBalances adapter")
        self.usdc_address = usdc_address

        self._rpc_sem = asyncio.Semaphore(getattr(self.config, "max_calls", 5))
        self._rpc_delay = getattr(self.config, "rpc_delay", 0.15)  # seconds
        self._rpc_jitter = getattr(self.config, "rpc_jitter", 0.10)  # seconds

    @backoff.on_exception(
        backoff.expo, (ProviderConnectionError), max_time=30, jitter=backoff.full_jitter
    )
    async def _rpc(self, fn, *args, **kwargs):
        """Throttle + backoff a single RPC."""
        async with self._rpc_sem:
            try:
                return await asyncio.to_thread(fn, *args, **kwargs)
            finally:
                delay = self._rpc_delay + random.random() * self._rpc_jitter
                if delay > 0:
                    await asyncio.sleep(delay)

    @property
    def adapter_name(self) -> str:
        return "idle_balances"

    @property
    def chain(self) -> AdapterChain:
        return (
            AdapterChain.HYPERLIQUID
            if self._chain == "hyperliquid"
            else AdapterChain.VAULT_CHAIN
        )

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch idle balances for the given subvault on the configured chain.

        Args:
            subvault_address: The specific subvault contract address to query

        Returns:
            List of AssetData objects containing asset addresses and balances
        """
        if self._chain == "hyperliquid":
            logger.debug(
                "Fetching HL USDC idle balance for subvault %s",
                subvault_address,
            )
            hyperliquid_usdc_address = getattr(
                self.config, "hyperliquid_usdc_address", None
            )
            if hyperliquid_usdc_address is None:
                raise RuntimeError(
                    "Hyperliquid USDC address is not configured. Re-enable Hyperliquid support before using this adapter."
                )
            usdc_address = hyperliquid_usdc_address
            usdc_asset = await self._fetch_asset_balance(
                self.w3, subvault_address, usdc_address
            )
            # For reporting purposes, we translate the Hyperliquid USDC address to the canonical L1 USDC address.
            # This ensures consistency in asset reporting across chains.
            usdc_asset = AssetData(
                asset_address=self.usdc_address, amount=usdc_asset.amount
            )
            return [usdc_asset]

        supported_assets = await self._fetch_supported_assets()

        logger.debug(
            "Fetching L1 balances for subvault %s across %d assets",
            subvault_address,
            len(supported_assets),
        )

        asset_tasks = [
            self._fetch_asset_balance(self.w3, subvault_address, asset_addr)
            for asset_addr in supported_assets
        ]

        assets = list(await asyncio.gather(*asset_tasks))

        logger.debug("Fetched %d L1 asset balances for subvault", len(assets))
        return assets

    async def fetch_all_assets(self) -> list[AssetData]:
        """Fetch idle balances for the main vault and ALL subvaults on the configured chain.

        This method discovers all subvaults and fetches idle balances for each,
        including the main vault contract itself.
        Use this for the default idle_balances collection on L1.

        Returns:
            List of AssetData objects from main vault and all subvaults
        """
        subvault_addresses = await self._fetch_subvault_addresses()
        vault_addresses = [self.config.vault_address_required] + subvault_addresses
        logger.info(
            "Fetching %s idle balances for main vault + %d subvaults",
            self._chain,
            len(subvault_addresses),
        )

        asset_results = await asyncio.gather(
            *[self.fetch_assets(addr) for addr in vault_addresses],
            return_exceptions=True,
        )

        all_assets: list[AssetData] = []
        for vault_addr, result in zip(vault_addresses, asset_results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to fetch idle balances for vault/subvault %s: %s",
                    vault_addr,
                    result,
                )
            elif isinstance(result, list):
                all_assets.extend(result)

        logger.info(
            "Fetched %d total idle balance entries from main vault + %d subvaults",
            len(all_assets),
            len(subvault_addresses),
        )
        return all_assets

    async def _fetch_contract_list(
        self,
        contract_address: str,
        abi: list,
        count_function: str,
        item_function: str,
        item_type: str,
    ) -> list[str]:
        """Generic method to fetch a list of items from a contract.

        Args:
            contract_address: The contract address to query
            abi: The contract ABI
            count_function: Name of the function that returns the count
            item_function: Name of the function that returns an item at index
            item_type: Description for logging (e.g., "subvault", "supported asset")

        Returns:
            List of addresses fetched from the contract
        """
        checksum_address = self.w3.to_checksum_address(contract_address)
        logger.debug("Fetching %ss from contract: %s", item_type, checksum_address)

        contract = self.w3.eth.contract(address=checksum_address, abi=abi)
        count = await self._rpc(
            getattr(contract.functions, count_function)().call,
            block_identifier=self.block_number,
        )
        logger.debug("Found %d %ss", count, item_type)

        async def fetch_item_at(index: int) -> str:
            item: str = await self._rpc(
                getattr(contract.functions, item_function)(index).call,
                block_identifier=self.block_number,
            )
            logger.debug("%s %d: %s", item_type.capitalize(), index, item)
            return item

        items = await asyncio.gather(*[fetch_item_at(i) for i in range(count)])

        logger.debug("Retrieved %d %ss", len(items), item_type)
        return list(items)

    async def _fetch_subvault_addresses(self) -> list[str]:
        """Get the subvault addresses for the given vault."""
        vault_abi = load_vault_abi()
        return await self._fetch_contract_list(
            contract_address=self.config.vault_address_required,
            abi=vault_abi,
            count_function="subvaults",
            item_function="subvaultAt",
            item_type="subvault",
        )

    async def _fetch_supported_assets(self) -> list[str]:
        """Get the supported assets for the given vault."""
        oracle_abi = load_oracle_abi()
        oracle_address = get_oracle_address_from_vault(
            self.config.vault_address_required, self.config.vault_rpc_required
        )
        return await self._fetch_contract_list(
            contract_address=oracle_address,
            abi=oracle_abi,
            count_function="supportedAssets",
            item_function="supportedAssetAt",
            item_type="supported asset",
        )

    async def _fetch_asset_balance(
        self, w3: Web3, subvault_address: str, asset_address: str
    ) -> AssetData:
        """Fetch the balance of an asset for the given subvault."""
        checksum_subvault_address = w3.to_checksum_address(subvault_address)

        if asset_address == self.eth_address:
            balance = await self._rpc(
                w3.eth.get_balance,
                checksum_subvault_address,
                block_identifier=self.block_number,
            )
        else:
            erc20_abi = load_erc20_abi()
            checksum_asset_address = w3.to_checksum_address(asset_address)
            erc20_contract = w3.eth.contract(
                address=checksum_asset_address, abi=erc20_abi
            )
            balance = await self._rpc(
                erc20_contract.functions.balanceOf(checksum_subvault_address).call,
                block_identifier=self.block_number,
            )

        return AssetData(asset_address=asset_address, amount=balance)
