from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AssetData, BaseAssetAdapter

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class HyperliquidAdapter(BaseAssetAdapter):
    """Adapter for querying Hyperliquid protocol assets."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.rpc_url = config.hl_rpc
        self.testnet = config.testnet

    @property
    def adapter_name(self) -> str:
        return "hyperliquid"

    async def fetch_assets(self, vault_address: str) -> list[AssetData]:
        """Fetch asset data from Hyperliquid for the given vault.

        Args:
            vault_address: The vault contract address to query

        Returns:
            Account portfolio value

        TODO: Implement actual Hyperliquid API calls
        """
        return []
