from __future__ import annotations

import logging

from web3 import Web3

from ...abi import load_aggregator_abi
from ...constants import (
    PRICE_FEED_ETH_USD,
    PRICE_FEED_USDC_ETH,
    PRICE_FEED_USDS_USD,
    PRICE_FEED_USDT_ETH,
    PRICE_FEED_WSTETH_ETH_BASE,
)
from ...settings import OracleSettings
from ...units import scale_to_18
from .base import BasePriceAdapter, PriceData

logger = logging.getLogger(__name__)


class ChainlinkAdapter(BasePriceAdapter):
    """Adapter for querying Chainlink price feeds."""

    eth_address: str

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.vault_rpc = config.vault_rpc
        self.block_number = config.block_number_required
        assets = config.assets
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for Chainlink adapter")
        self.eth_address = eth_address
        self.usdc_address = assets["USDC"]
        self.usdt_address = assets["USDT"]
        self.usds_address = assets["USDS"]
        self.wsteth_address = assets["WSTETH"]

    @property
    def adapter_name(self) -> str:
        return "chainlink"

    async def latest_price_and_decimals(self, feed_contract) -> tuple[int, int]:
        _, answer, _, _, _ = feed_contract.functions.latestRoundData().call(
            block_identifier=self.block_number
        )
        decimals = feed_contract.functions.decimals().call(
            block_identifier=self.block_number
        )
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
        if prices_accumulator.base_asset != self.eth_address:
            raise ValueError("Chainlink adapter only supports ETH as base asset")

        direct_feed_assets = [
            (self.usdc_address, PRICE_FEED_USDC_ETH),
            (self.usdt_address, PRICE_FEED_USDT_ETH),
            (self.wsteth_address, PRICE_FEED_WSTETH_ETH_BASE),
        ]
        logger.debug(f" Asset addresses to check: {asset_addresses}")
        checksummed_asset_addresses = [
            Web3.to_checksum_address(addr) for addr in asset_addresses
        ]

        direct_feed_assets = [
            (Web3.to_checksum_address(asset_address), price_feed)
            for asset_address, price_feed in direct_feed_assets
            if asset_address
            and Web3.to_checksum_address(asset_address) in checksummed_asset_addresses
        ]

        has_usds = (
            self.usds_address
            and Web3.to_checksum_address(self.usds_address)
            in checksummed_asset_addresses
            if self.usds_address
            else False
        )

        if not direct_feed_assets and not has_usds:
            return prices_accumulator

        w3 = Web3(Web3.HTTPProvider(self.vault_rpc))
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

        self.validate_prices(prices_accumulator)

        return prices_accumulator
