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
    PRICE_FEED_APE_ETH = "0xc7de7f4d4C9c991fF62a07D18b3E31e349833A18"
    PRICE_FEED_USDC_USD = "0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6"

    ETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    APE = "0x4d224452801ACEd8B2F0aebE155379bb5D594381"

    DIRECT_PRICE_FEEDS_ADDRESSES = {
        APE: PRICE_FEED_APE_ETH,
    }

    INDIRECT_PRICE_FEEDS_ADDRESSES = {
        USDC: PRICE_FEED_USDC_USD,
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

        supported_assets = set(self.DIRECT_PRICE_FEEDS_ADDRESSES.keys()) | set(
            self.INDIRECT_PRICE_FEEDS_ADDRESSES.keys()
        )

        for asset_address in asset_addresses:
            if asset_address not in supported_assets:
                raise ValueError(f"Asset {asset_address} is not supported")

        w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
        aggregator_abi = load_aggregator_abi()

        direct_price_feeds = {
            asset_address: w3.eth.contract(
                address=self.DIRECT_PRICE_FEEDS_ADDRESSES[asset_address],
                abi=aggregator_abi,
            )
            for asset_address in asset_addresses
            if asset_address in self.DIRECT_PRICE_FEEDS_ADDRESSES
        }

        indirect_price_feeds = {
            asset_address: w3.eth.contract(
                address=self.INDIRECT_PRICE_FEEDS_ADDRESSES[asset_address],
                abi=aggregator_abi,
            )
            for asset_address in asset_addresses
            if asset_address in self.INDIRECT_PRICE_FEEDS_ADDRESSES
        }

        return []
