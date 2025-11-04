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

        self._address_to_symbol: dict[str, str] = {}
        for symbol, address in config.assets.items():
            if isinstance(address, str) and address:
                self._address_to_symbol[self._canonical_address(address)] = symbol

    @property
    def adapter_name(self) -> str:
        return "pyth"

    async def _resolve_feed_id(self, symbol: str, quote: str = "USD") -> str | None:
        """Resolve feed ID using cache → Hermes discovery → constants fallback.

        Args:
            symbol: Asset symbol (e.g., "WSTETH")
            quote: Quote currency (default: "USD")

        Returns:
            Feed ID with 0x prefix, or None if not found
        """
        feed_id = await self._discover_feed_from_api(symbol, quote)
        if feed_id:
            return feed_id

        fallback = PYTH_PRICE_FEED_IDS.get(f"{symbol}/{quote}")
        if fallback:
            logger.warning("Falling back to statically configured feed ID for %s/%s", symbol, quote)
            return fallback

        logger.warning("No feed ID found for %s/%s", symbol, quote)
        return None

    def _canonical_address(self, address: str) -> str:
        """Return a canonical representation of an address for comparisons."""
        try:
            return Web3.to_checksum_address(address)
        except ValueError:
            return address.lower()

    async def _discover_feed_from_api(
        self, symbol: str, quote: str = "USD"
    ) -> str | None:
        """Query Pyth API to discover feed ID for symbol.

        Args:
            symbol: Asset symbol (e.g., "WSTETH")
            quote: Quote currency (default: "USD")

        Returns:
            Feed ID with 0x prefix, or None if not found
        """
        query = f"{symbol.lower()}%2F{quote.lower()}"
        url = f"{self.hermes_endpoint}/v2/price_feeds?query={query}&asset_type=crypto"

        try:
            response = await asyncio.to_thread(lambda: requests.get(url, timeout=2.0))
            response.raise_for_status()
        except (
            Exception
        ) as exc:  # pragma: no cover - network failures already logged elsewhere
            logger.error("Feed discovery failed for %s/%s: %s", symbol, quote, exc)
            return None

        feeds = response.json()
        matches = [
            ((feed.get("type") or "unknown").lower(), f"0x{feed['id']}")
            for feed in feeds
            if (feed.get("attributes", {}).get("base", "").upper() == symbol.upper())
            and (
                feed.get("attributes", {}).get("quote_currency", "").upper()
                == quote.upper()
            )
        ]

        for preferred in ("derived", "pythnet"):
            for feed_type, feed_id in matches:
                if feed_type == preferred:
                    logger.info(
                        "Discovered feed for %s/%s: %s (type: %s)",
                        symbol,
                        quote,
                        feed_id,
                        feed_type,
                    )
                    return feed_id

        if matches:
            feed_type, feed_id = matches[0]
            logger.info(
                "Discovered feed for %s/%s: %s (type: %s)",
                symbol,
                quote,
                feed_id,
                feed_type,
            )
            return feed_id

        logger.warning(
            "No exact match found for %s/%s in %d results",
            symbol,
            quote,
            len(feeds),
        )
        return None

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices from Pyth Network.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                use the pipeline's base asset address. All prices are 18-decimal
                fixed-point values representing base-asset units per 1 unit of
                the asset.

        Returns:
            The same accumulator with Pyth-derived prices merged in.
        """

        base_address = self._canonical_address(prices_accumulator.base_asset)
        base_symbol = self._symbol_for(base_address)
        if not base_symbol:
            raise ValueError(
                f"Base asset {prices_accumulator.base_asset} is not recognized by Pyth adapter configuration"
            )

        base_feed_id = await self._resolve_feed_id(base_symbol, "USD")
        if not base_feed_id:
            raise ValueError(
                f"{base_symbol}/USD price feed could not be resolved from Pyth Hermes"
            )

        assets_to_fetch: dict[str, tuple[str, str, str]] = {}
        for address in asset_addresses:
            canonical = self._canonical_address(address)
            if canonical == base_address:
                continue

            symbol = self._symbol_for(canonical)
            if not symbol:
                logger.warning(
                    "Address %s not recognized in adapter configuration, skipping",
                    address,
                )
                continue

            feed_id = await self._resolve_feed_id(symbol, "USD")
            if not feed_id:
                logger.warning("Could not resolve feed ID for %s/USD, skipping", symbol)
                continue

            assets_to_fetch[canonical] = (address, symbol, feed_id)

        if not assets_to_fetch:
            return prices_accumulator

        all_feed_ids = [base_feed_id] + [
            feed_id for _, _, feed_id in assets_to_fetch.values()
        ]
        query = "&".join(f"ids[]={fid}" for fid in all_feed_ids)
        url = f"{self.hermes_endpoint}/v2/updates/price/latest?{query}"

        response = await asyncio.to_thread(lambda: requests.get(url, timeout=2.0))
        response.raise_for_status()
        parsed_feeds = response.json().get("parsed", [])
        feeds_by_id = {feed.get("id"): feed for feed in parsed_feeds}

        logger.debug(" Received %d price feeds", len(parsed_feeds))

        base_feed_key = base_feed_id.removeprefix("0x")
        base_feed = feeds_by_id.get(base_feed_key)
        if not base_feed:
            raise ValueError(f"{base_symbol}/USD price feed not found in Pyth response")

        base_price_obj = base_feed.get("price", {})
        base_publish_time = base_price_obj.get("publish_time", 0)
        current_time = int(time.time())

        if (current_time - base_publish_time) > self.staleness_threshold:
            age = current_time - base_publish_time
            raise ValueError(f"{base_symbol}/USD price is stale (age: {age}s)")

        base_usd_price = self._parse_price_to_18_decimals(base_price_obj)
        self._check_confidence(base_price_obj, base_usd_price, f"{base_symbol}/USD")
        logger.debug(" %s/USD price: $%.6f", base_symbol, base_usd_price / 10**18)

        for canonical, (original_address, symbol, feed_id) in assets_to_fetch.items():
            feed_key = feed_id.removeprefix("0x")
            asset_feed = feeds_by_id.get(feed_key)
            if not asset_feed:
                logger.warning(" Price feed for %s/USD not found", symbol)
                continue

            price_obj = asset_feed.get("price", {})
            publish_time = price_obj.get("publish_time", 0)
            if (current_time - publish_time) > self.staleness_threshold:
                logger.warning(
                    " %s/USD price is stale (age: %ss), skipping",
                    symbol,
                    current_time - publish_time,
                )
                continue

            usd_price = self._parse_price_to_18_decimals(price_obj)
            self._check_confidence(price_obj, usd_price, f"{symbol}/USD")

            asset_price = (usd_price * 10**18) // base_usd_price
            prices_accumulator.prices[original_address] = asset_price
            logger.debug(
                " %s: $%.6f = %s %s",
                symbol,
                usd_price / 10**18,
                asset_price,
                base_symbol,
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

    def _symbol_for(self, address: str) -> str | None:
        return self._address_to_symbol.get(self._canonical_address(address))
