from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import Web3

from ...logger import get_logger
from ...abi import load_vault_abi
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

        subvault_addresses = []
        for i in range(subvault_count):
            subvault_address = vault_contract.functions.subvaultAt(i).call()
            logger.debug("Subvault %d: %s", i, subvault_address)
            subvault_addresses.append(subvault_address)

        logger.debug("Retrieved %d subvault addresses", len(subvault_addresses))
        return subvault_addresses
