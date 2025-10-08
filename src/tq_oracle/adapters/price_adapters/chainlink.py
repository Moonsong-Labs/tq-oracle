from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import Web3

from ...abi import load_aggregator_abi

from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class ChainlinkAdapter(BasePriceAdapter):
    """Adapter for querying Chainlink price feeds."""

    PRICE_FEED_ETH_USD = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"

    USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

    PRICE_FEED_ADDRESSES = {
        USDC: PRICE_FEED_ETH_USD,
    }

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
        """

        for asset_address in asset_addresses:
            if asset_address not in self.PRICE_FEED_ADDRESSES:
                raise ValueError(
                    f"Asset address {asset_address} not in PRICE_FEED_ADDRESSES"
                )

        w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
        aggregator_abi = load_aggregator_abi()

        price_feeds = {
            asset_address: w3.eth.contract(
                address=self.PRICE_FEED_ADDRESSES[asset_address],
                abi=aggregator_abi,
            )
            for asset_address in asset_addresses
        }

        return []
