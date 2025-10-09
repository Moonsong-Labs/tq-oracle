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
