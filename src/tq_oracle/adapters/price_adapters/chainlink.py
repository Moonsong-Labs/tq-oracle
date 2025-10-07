from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class ChainlinkAdapter(BasePriceAdapter):
    """Adapter for querying Chainlink price feeds."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.l1_rpc = config.l1_rpc

    @property
    def adapter_name(self) -> str:
        return "chainlink"

    async def fetch_prices(self, asset_addresses: list[str]) -> list[PriceData]:
        """Fetch asset prices from Chainlink price feeds.

        Args:
            asset_addresses: List of asset contract addresses to get prices for

        Returns:
            List of price data from Chainlink

        TODO: Implement actual Chainlink price feed queries
        """
        return []
