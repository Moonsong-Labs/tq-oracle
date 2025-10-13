from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from web3 import Web3
import backoff
import random
from web3.exceptions import ProviderConnectionError
from ...constants import (
    ETH_ASSET,
    USDC_HL_MAINNET,
    USDC_HL_TESTNET,
    USDC_MAINNET,
    USDC_SEPOLIA,
)
from ...logger import get_logger
from ...abi import (
    load_vault_abi,
    load_oracle_abi,
    get_oracle_address_from_vault,
    load_erc20_abi,
)
from .base import AssetData, BaseAssetAdapter

if TYPE_CHECKING:
    from ...config import OracleCLIConfig

logger = get_logger(__name__)


class IdleBalancesAdapter(BaseAssetAdapter):
    """Adapter for querying Idle Balances assets."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.w3_mainnet = Web3(Web3.HTTPProvider(config.l1_rpc))
        self.w3_hl: Optional[Web3] = None
        if config.hl_rpc:
            self.w3_hl = Web3(Web3.HTTPProvider(config.hl_rpc))
        self._rpc_sem = asyncio.Semaphore(getattr(self.config, "max_calls", 3))
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

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch asset data from Idle Balances for the given vault.

        Args:
            subvault_address: The subvault contract address to query (used as fallback if config doesn't specify hl_subvault_address)

        Returns:
            List of AssetData objects containing asset addresses and balances
        """
        subvault_addresses, supported_assets = await asyncio.gather(
            self._fetch_subvault_addresses(),
            self._fetch_supported_assets(),
        )

        logger.debug(
            "Fetching balances for %d subvaults x %d assets = %d total calls",
            len(subvault_addresses),
            len(supported_assets),
            len(subvault_addresses) * len(supported_assets),
        )

        asset_tasks = [
            self._fetch_asset_balance(self.w3_mainnet, subvault_addr, asset_addr)
            for subvault_addr in subvault_addresses
            for asset_addr in supported_assets
        ]

        assets = list(await asyncio.gather(*asset_tasks))

        # Fetch USDC balance from HL subvault if configured
        if self.w3_hl:
            usdc_address = USDC_HL_TESTNET if self.config.testnet else USDC_HL_MAINNET
            hl_subvault_address = self.config.hl_subvault_address or subvault_address
            usdc_asset = await self._fetch_asset_balance(
                self.w3_hl, hl_subvault_address, usdc_address
            )
            # Overwrite USDC HL address with mainnet address
            usdc_asset.asset_address = (
                USDC_SEPOLIA if self.config.testnet else USDC_MAINNET
            )
            assets.append(usdc_asset)
        else:
            logger.warning(
                "Hyperliquid RPC not configured, skipping HL USDC balance fetch"
            )

        logger.debug("Fetched %d asset balances", len(assets))
        return assets

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
        checksum_address = self.w3_mainnet.to_checksum_address(contract_address)
        logger.debug("Fetching %ss from contract: %s", item_type, checksum_address)

        contract = self.w3_mainnet.eth.contract(address=checksum_address, abi=abi)
        count = await self._rpc(getattr(contract.functions, count_function)().call)
        logger.debug("Found %d %ss", count, item_type)

        async def fetch_item_at(index: int) -> str:
            item: str = await self._rpc(
                getattr(contract.functions, item_function)(index).call
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
            contract_address=self.config.vault_address,
            abi=vault_abi,
            count_function="subvaults",
            item_function="subvaultAt",
            item_type="subvault",
        )

    async def _fetch_supported_assets(self) -> list[str]:
        """Get the supported assets for the given vault."""
        oracle_abi = load_oracle_abi()
        oracle_address = get_oracle_address_from_vault(
            self.config.vault_address, self.config.l1_rpc
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

        if asset_address == ETH_ASSET:
            balance = await self._rpc(w3.eth.get_balance, checksum_subvault_address)
        else:
            erc20_abi = load_erc20_abi()
            checksum_asset_address = w3.to_checksum_address(asset_address)
            erc20_contract = w3.eth.contract(
                address=checksum_asset_address, abi=erc20_abi
            )
            balance = await self._rpc(
                erc20_contract.functions.balanceOf(checksum_subvault_address).call
            )

        return AssetData(asset_address=asset_address, amount=balance)
