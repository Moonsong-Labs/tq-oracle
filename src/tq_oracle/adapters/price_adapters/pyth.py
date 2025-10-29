from __future__ import annotations

import asyncio
import logging
import time

import requests
from web3 import Web3

from tq_oracle.constants import PYTH_PRICE_FEED_IDS
from tq_oracle.settings import OracleSettings

from .base import BasePriceAdapter, PriceData

logger = logging.getLogger(__name__)


class PythAdapter(BasePriceAdapter):
    """Adapter for querying Pyth Network price feeds."""

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.hermes_endpoint = config.pyth_hermes_endpoint
        self.staleness_threshold = config.pyth_staleness_threshold
        self.max_confidence_ratio = config.pyth_max_confidence_ratio
        eth_address = config.assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for Pyth adapter")
        self.eth_address = eth_address

    @property
    def adapter_name(self) -> str:
        return "pyth"

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices from Pyth Network.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                have base_asset set to ETH (wei). All prices are 18-decimal values
                representing wei per 1 unit of the asset.

        Returns:
            The same accumulator with Pyth-derived prices merged in.

        Notes:
            - Only ETH as base asset is supported.
            - Converts USD prices to ETH using ETH/USD feed.
            - Validates price staleness and confidence intervals.
        """
        if prices_accumulator.base_asset != self.eth_address:
            raise ValueError("Pyth adapter only supports ETH as base asset")

        feed_ids_to_fetch = ["ETH/USD"]
        asset_symbol_map: dict[str, str] = {}
        checksummed_asset_addresses = [
            Web3.to_checksum_address(addr) for addr in asset_addresses
        ]

        for symbol, address in self.config.assets.items():
            if address is None or f"{symbol}/USD" not in PYTH_PRICE_FEED_IDS:
                continue
            checksummed = Web3.to_checksum_address(address)
            if checksummed in checksummed_asset_addresses:
                feed_ids_to_fetch.append(f"{symbol}/USD")
                asset_symbol_map[checksummed] = symbol

        if not asset_symbol_map:
            return prices_accumulator

        logger.debug(f" Fetching prices for {len(feed_ids_to_fetch)} feeds")

        price_feed_ids = [PYTH_PRICE_FEED_IDS[f] for f in feed_ids_to_fetch]
        query = "&".join(f"ids[]={fid}" for fid in price_feed_ids)
        url = f"{self.hermes_endpoint}/v2/updates/price/latest?{query}"

        response = await asyncio.to_thread(lambda: requests.get(url, timeout=2.0))
        response.raise_for_status()
        parsed_feeds = response.json().get("parsed", [])

        logger.debug(f" Received {len(parsed_feeds)} price feeds")

        eth_feed = next(
            (
                f
                for f in parsed_feeds
                if f.get("id") == PYTH_PRICE_FEED_IDS["ETH/USD"].removeprefix("0x")
            ),
            None,
        )
        if not eth_feed:
            raise ValueError("ETH/USD price feed not found in Pyth response")

        eth_price_obj = eth_feed.get("price", {})
        eth_publish_time = eth_price_obj.get("publish_time", 0)
        current_time = int(time.time())

        if (current_time - eth_publish_time) > self.staleness_threshold:
            age = current_time - eth_publish_time
            raise ValueError(f"ETH/USD price is stale (age: {age}s)")

        eth_usd_price = self._parse_price_to_18_decimals(eth_price_obj)
        self._check_confidence(eth_price_obj, eth_usd_price, "ETH/USD")
        logger.debug(f" ETH/USD price: ${eth_usd_price / 10**18:.2f}")

        for asset_address, symbol in asset_symbol_map.items():
            feed_id = PYTH_PRICE_FEED_IDS.get(f"{symbol}/USD")
            if not feed_id:
                continue

            asset_feed = next(
                (f for f in parsed_feeds if f.get("id") == feed_id.removeprefix("0x")),
                None,
            )
            if not asset_feed:
                logger.warning(f" Price feed for {symbol}/USD not found")
                continue

            asset_price_obj = asset_feed.get("price", {})
            asset_publish_time = asset_price_obj.get("publish_time", 0)

            if (current_time - asset_publish_time) > self.staleness_threshold:
                logger.warning(
                    f" {symbol}/USD price is stale (age: {current_time - asset_publish_time}s), skipping"
                )
                continue

            pyth_asset_usd = self._parse_price_to_18_decimals(asset_price_obj)
            self._check_confidence(asset_price_obj, pyth_asset_usd, f"{symbol}/USD")

            asset_eth_price = (pyth_asset_usd * 10**18) // eth_usd_price
            prices_accumulator.prices[asset_address] = asset_eth_price
            logger.debug(
                f" {symbol}: ${pyth_asset_usd / 10**18:.6f} = {asset_eth_price} wei"
            )

        self.validate_prices(prices_accumulator)
        return prices_accumulator

    def _parse_price_to_18_decimals(self, price_obj: dict) -> int:
        """Parse Pyth price object to 18-decimal integer value.

        Args:
            price_obj: Pyth price object containing 'price' and 'expo' fields

        Returns:
            Price as integer with 18 decimal places

        Notes:
            Pyth returns prices as: actual_price = price * 10^expo
            This method converts to 18-decimal fixed-point representation
            using only integer arithmetic for maximum precision.
        """
        price_raw = int(price_obj.get("price", 0))
        expo = int(price_obj.get("expo", 0))

        current_decimals = -expo

        if current_decimals == 18:
            return price_raw
        elif current_decimals < 18:
            return price_raw * (10 ** (18 - current_decimals))
        else:
            return price_raw // (10 ** (current_decimals - 18))

    def _check_confidence(
        self, price_obj: dict, price_18_decimals: int, symbol: str
    ) -> None:
        """Check confidence ratio and log warning if too high.

        Args:
            price_obj: Pyth price object containing 'conf' and 'expo' fields
            price_18_decimals: Price as 18-decimal integer
            symbol: Symbol name for logging
        """
        conf_raw = int(price_obj.get("conf", 0))
        expo = int(price_obj.get("expo", 0))
        current_decimals = -expo

        if current_decimals == 18:
            conf_18 = conf_raw
        elif current_decimals < 18:
            conf_18 = conf_raw * (10 ** (18 - current_decimals))
        else:
            conf_18 = conf_raw // (10 ** (current_decimals - 18))

        conf_ratio = (conf_18 * 10000) // abs(price_18_decimals) / 10000

        if conf_ratio > self.max_confidence_ratio:
            logger.warning(
                f" {symbol} confidence ratio too high: {conf_ratio:.4f} "
                f"(max: {self.max_confidence_ratio})"
            )
