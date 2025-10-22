from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import Web3

from ...abi import load_aggregator_abi
from ...constants import (
    ETH_ASSET,
    USDC_MAINNET,
    PRICE_FEED_USDC_ETH,
    USDC_SEPOLIA,
    USDT_MAINNET,
    PRICE_FEED_USDT_ETH,
    USDS_MAINNET,
    PRICE_FEED_USDS_USD,
    PRICE_FEED_ETH_USD,
)
from ...units import scale_to_18

from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class ChainlinkAdapter(BasePriceAdapter):
    """Adapter for querying Chainlink price feeds."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.l1_rpc = config.l1_rpc
        self.usdc_address = USDC_SEPOLIA if config.testnet else USDC_MAINNET
        self.usdt_address = None if config.testnet else USDT_MAINNET
        self.usds_address = None if config.testnet else USDS_MAINNET

    @property
    def adapter_name(self) -> str:
        return "chainlink"

    async def latest_price_and_decimals(self, feed_contract) -> tuple[int, int]:
        _, answer, _, _, _ = feed_contract.functions.latestRoundData().call()
        decimals = feed_contract.functions.decimals().call()
        return int(answer), int(decimals)

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices from Chainlink price feeds.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                have base_asset set to ETH (wei). All prices are 18-decimal values
                representing wei per 1 unit of the asset.

        Returns:
            The same accumulator with Chainlink-derived prices merged in.

        Notes:
            - Only ETH as base asset is supported.
            - For assets without direct ETH price feeds, derives prices by
              combining USD-denominated feeds (e.g., USDS/USD ÷ ETH/USD).
        """
        if prices_accumulator.base_asset != ETH_ASSET:
            raise ValueError("Chainlink adapter only supports ETH as base asset")

        direct_feed_assets = [
            (self.usdc_address, PRICE_FEED_USDC_ETH),
            (self.usdt_address, PRICE_FEED_USDT_ETH),
        ]

        direct_feed_assets = [
            (asset_address, price_feed)
            for asset_address, price_feed in direct_feed_assets
            if asset_address and asset_address in asset_addresses
        ]

        has_usds = self.usds_address and self.usds_address in asset_addresses

        if not direct_feed_assets and not has_usds:
            return prices_accumulator

        w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
        aggregator_abi = load_aggregator_abi()

        for asset_address, price_feed in direct_feed_assets:
            feed_contract = w3.eth.contract(
                address=w3.to_checksum_address(price_feed),
                abi=aggregator_abi,
            )

            answer, decimals = await self.latest_price_and_decimals(feed_contract)
            scaled_price = scale_to_18(answer, decimals)
            prices_accumulator.prices[asset_address] = scaled_price

        if has_usds and self.usds_address:
            usds_usd_feed = w3.eth.contract(
                address=w3.to_checksum_address(PRICE_FEED_USDS_USD),
                abi=aggregator_abi,
            )
            eth_usd_feed = w3.eth.contract(
                address=w3.to_checksum_address(PRICE_FEED_ETH_USD),
                abi=aggregator_abi,
            )

            usds_usd_answer, usds_usd_decimals = await self.latest_price_and_decimals(
                usds_usd_feed
            )
            eth_usd_answer, eth_usd_decimals = await self.latest_price_and_decimals(
                eth_usd_feed
            )

            usds_usd_scaled = scale_to_18(usds_usd_answer, usds_usd_decimals)
            eth_usd_scaled = scale_to_18(eth_usd_answer, eth_usd_decimals)

            usds_eth_price = (usds_usd_scaled * 10**18) // eth_usd_scaled
            prices_accumulator.prices[self.usds_address] = usds_eth_price

        await self.validate_prices(prices_accumulator)

        return prices_accumulator
