from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from web3 import Web3

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
        self.w3_hl = Web3(Web3.HTTPProvider(config.hl_rpc))

    @property
    def adapter_name(self) -> str:
        return "idle_balances"

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch asset data from Idle Balances for the given vault."""
        return []

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
        count = getattr(contract.functions, count_function)().call()
        logger.debug("Found %d %ss", count, item_type)

        async def fetch_item_at(index: int) -> str:
            item = await asyncio.to_thread(
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
    ) -> int:
        """Fetch the balance of an asset for the given subvault."""
        erc20_abi = load_erc20_abi()
        erc20_contract = w3.eth.contract(address=asset_address, abi=erc20_abi)
        return erc20_contract.functions.balanceOf(subvault_address).call()
