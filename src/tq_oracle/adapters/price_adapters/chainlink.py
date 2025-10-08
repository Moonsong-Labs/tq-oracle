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

    async def latest_price_and_decimals(self, feed_contract) -> tuple[int, int]:
        _, answer, _, _, _ = feed_contract.functions.latestRoundData().call()
        decimals = feed_contract.functions.decimals().call()
        return int(answer), int(decimals)

    def scale_to_18(self, value: int, decimals: int) -> int:
        if decimals == 18:
            return value
        if decimals < 18:
            return value * (10 ** (18 - decimals))
        return value // (10 ** (decimals - 18))

    async def fetch_prices(self, asset_addresses: list[str]) -> PriceData:
        """Fetch asset prices from Chainlink price feeds.

        Args:
            asset_addresses: List of asset contract addresses to get prices for

        Returns:
            List of price data from Chainlink
        """

        supported_assets = (
            set(self.DIRECT_PRICE_FEEDS_ADDRESSES.keys())
            | set(self.INDIRECT_PRICE_FEEDS_ADDRESSES.keys())
            | {self.ETH}
        )

        for asset_address in asset_addresses:
            if asset_address not in supported_assets:
                raise ValueError(f"Asset {asset_address} is not supported")

        w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
        aggregator_abi = load_aggregator_abi()

        direct_price_feeds = {
            asset_address: w3.eth.contract(
                address=w3.to_checksum_address(
                    self.DIRECT_PRICE_FEEDS_ADDRESSES[asset_address]
                ),
                abi=aggregator_abi,
            )
            for asset_address in asset_addresses
            if asset_address in self.DIRECT_PRICE_FEEDS_ADDRESSES
        }

        indirect_price_feeds = {
            asset_address: w3.eth.contract(
                address=w3.to_checksum_address(
                    self.INDIRECT_PRICE_FEEDS_ADDRESSES[asset_address]
                ),
                abi=aggregator_abi,
            )
            for asset_address in asset_addresses
            if asset_address in self.INDIRECT_PRICE_FEEDS_ADDRESSES
        }

        # Always need ETH/USD for indirect conversions
        eth_usd_feed = w3.eth.contract(
            address=w3.to_checksum_address(self.PRICE_FEED_ETH_USD),
            abi=aggregator_abi,
        )

        prices = {}

        eth_usd_answer, eth_usd_decimals = await self.latest_price_and_decimals(
            eth_usd_feed
        )

        eth_usd_scaled = self.scale_to_18(
            eth_usd_answer, eth_usd_decimals
        )  # USD per ETH in 18d

        for asset in asset_addresses:
            if asset == self.ETH:
                prices[asset] = 10**18
                continue

            if asset in direct_price_feeds:
                ans, dec = await self.latest_price_and_decimals(
                    direct_price_feeds[asset]
                )
                if ans <= 0:
                    raise ValueError(
                        f"Direct feed for {asset} returned non-positive answer"
                    )
                price_in_eth_18 = self.scale_to_18(ans, dec)
                prices[asset] = price_in_eth_18
                continue

            if asset in indirect_price_feeds:
                ans, dec = await self.latest_price_and_decimals(
                    indirect_price_feeds[asset]
                )
                if ans <= 0:
                    raise ValueError(
                        f"Indirect feed for {asset} returned non-positive answer"
                    )
                asset_usd_18 = self.scale_to_18(ans, dec)  # USD per asset, 18d
                price_in_eth_18 = (asset_usd_18 * (10**18)) // eth_usd_scaled
                prices[asset] = price_in_eth_18
                continue

            # Should not reach here due to earlier validation
            raise ValueError(f"Asset {asset} is not supported")

        return PriceData(base_asset=self.ETH, prices=prices)
