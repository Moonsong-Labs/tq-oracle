from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from web3 import Web3

from ...logger import get_logger
from ...abi import load_vault_abi, load_oracle_abi, get_oracle_address_from_vault
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

    async def fetch_subvault_addresses(self) -> list[str]:
        """Get the subvault addresses for the given vault."""
        vault_abi = load_vault_abi()
        vault_address = self.w3_mainnet.to_checksum_address(self.config.vault_address)
        logger.debug("Fetching subvault addresses for vault: %s", vault_address)

        vault_contract = self.w3_mainnet.eth.contract(
            address=vault_address, abi=vault_abi
        )
        subvault_count = vault_contract.functions.subvaults().call()
        logger.debug("Found %d subvaults", subvault_count)

        async def fetch_subvault_at(index: int) -> str:
            address = await asyncio.to_thread(
                vault_contract.functions.subvaultAt(index).call
            )
            logger.debug("Subvault %d: %s", index, address)
            return address

        subvault_addresses = await asyncio.gather(
            *[fetch_subvault_at(i) for i in range(subvault_count)]
        )

        logger.debug("Retrieved %d subvault addresses", len(subvault_addresses))
        return list(subvault_addresses)

    async def fetch_supported_assets(self) -> list[str]:
        """Get the supported assets for the given vault."""
        oracle_abi = load_oracle_abi()
        oracle_address = get_oracle_address_from_vault(
            self.config.vault_address, self.config.l1_rpc
        )
        logger.debug("Fetching supported assets for oracle: %s", oracle_address)

        oracle_contract = self.w3_mainnet.eth.contract(
            address=oracle_address, abi=oracle_abi
        )
        supported_asset_count = oracle_contract.functions.supportedAssets().call()
        logger.debug("Found %d supported assets", supported_asset_count)

        async def fetch_supported_asset_at(index: int) -> str:
            asset = await asyncio.to_thread(
                oracle_contract.functions.supportedAssetAt(index).call
            )
            logger.debug("Supported asset %d: %s", index, asset)
            return asset

        supported_assets = await asyncio.gather(
            *[fetch_supported_asset_at(i) for i in range(supported_asset_count)]
        )

        logger.debug("Retrieved %d supported assets", len(supported_assets))
        return list(supported_assets)
