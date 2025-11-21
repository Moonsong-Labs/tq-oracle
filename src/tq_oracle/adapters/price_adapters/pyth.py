from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlencode

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

        self._address_to_symbol: dict[str, str] = {
            self._canonical_address(addr): sym
            for sym, addr in config.assets.items()
            if isinstance(addr, str) and addr
        }
        self._feed_ids: dict[str, str] = {}

    @property
    def adapter_name(self) -> str:
        return "pyth"

    def _canonical_address(self, address: str) -> str:
        try:
            return Web3.to_checksum_address(address)
        except ValueError:
            return address.lower()

    def _scale_to_18(self, value: int, expo: int) -> int:
        """Scale an integer `value * 10**expo` to 18-decimal fixed point.

        Raises:
            ValueError: If value is negative, expo is out of range |24|.
        """
        if value < 0:
            raise ValueError(f"Price value must be non-negative, got {value}")
        if not (-24 <= expo <= 24):
            raise ValueError(f"Exponent {expo} out of supported range [-24, 24]")

        shift = 18 + expo
        scaled = value * (10**shift) if shift >= 0 else value // (10**-shift)
        return scaled

    async def _http_get(self, url: str, *, params: dict | None = None):
        return await asyncio.to_thread(
            lambda: requests.get(url, params=params, timeout=2.0)
        )

    async def _resolve_feed_id(self, symbol: str, quote: str = "USD") -> str | None:
        key = f"{symbol.upper()}/{quote.upper()}"
        cached = self._feed_ids.get(key)
        if cached:
            return cached

        resolved = await self._discover_feed_from_api(symbol, quote)
        if resolved:
            self._feed_ids[key] = resolved
            return resolved

        fallback = PYTH_PRICE_FEED_IDS.get(key)
        if fallback:
            self._feed_ids[key] = fallback
            logger.warning("Falling back to static feed ID for %s", key)
            return fallback

        logger.warning("No feed ID found for %s", key)
        return None

    async def _discover_feed_from_api(
        self, symbol: str, quote: str = "USD"
    ) -> str | None:
        url = f"{self.hermes_endpoint}/v2/price_feeds"
        try:
            r = await self._http_get(
                url,
                params={"query": f"{symbol}/{quote}".lower(), "asset_type": "crypto"},
            )
            r.raise_for_status()
        except Exception as exc:  # pragma: no cover
            logger.error("Feed discovery failed for %s/%s: %s", symbol, quote, exc)
            return None

        feeds = r.json()
        if not isinstance(feeds, list):
            logger.debug(
                "Unexpected feed discovery payload for %s/%s; skipping dynamic resolution",
                symbol,
                quote,
            )
            return None
        sym_u, quo_u = symbol.upper(), quote.upper()
        matches = [
            ((feed.get("type") or "unknown").lower(), f"0x{feed['id']}")
            for feed in feeds
            if feed.get("attributes", {}).get("base", "").upper() == sym_u
            and feed.get("attributes", {}).get("quote_currency", "").upper() == quo_u
        ]
        if not matches:
            logger.warning(
                "No exact match found for %s/%s in %d results",
                symbol,
                quote,
                len(feeds) if isinstance(feeds, list) else 0,
            )
            return None

        pref_rank = {"derived": 0, "pythnet": 1}  # tweak order if desired
        feed_type, feed_id = sorted(matches, key=lambda t: pref_rank.get(t[0], 99))[0]
        logger.info(
            "Discovered feed for %s/%s: %s (type: %s)",
            symbol,
            quote,
            feed_id,
            feed_type,
        )
        return feed_id

    def _check_confidence(self, price_obj: dict, price_18: int, symbol: str) -> None:
        conf_18 = self._scale_to_18(
            int(price_obj.get("conf", 0)), int(price_obj.get("expo", 0))
        )
        denom = abs(price_18)
        if denom == 0:
            raise ValueError(f"{symbol} price is zero")
        conf_ratio = conf_18 / denom
        if conf_ratio > self.max_confidence_ratio:
            raise ValueError(
                f"{symbol} confidence ratio {conf_ratio:.4f} exceeds maximum {self.max_confidence_ratio}"
            )

    def _symbol_for(self, address: str) -> str | None:
        return self._address_to_symbol.get(self._canonical_address(address))

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        base_address = self._canonical_address(prices_accumulator.base_asset)
        base_symbol = self._symbol_for(base_address)
        if not base_symbol:
            raise ValueError(
                f"Base asset {prices_accumulator.base_asset} not recognized by Pyth adapter configuration"
            )

        base_feed_id = await self._resolve_feed_id(base_symbol, "USD")
        if not base_feed_id:
            raise ValueError(
                f"{base_symbol}/USD price feed could not be resolved from Pyth Hermes"
            )

        canonical_to_original: dict[str, str] = {}
        for address in asset_addresses:
            canonical_address = self._canonical_address(address)
            if canonical_address != base_address:
                canonical_to_original.setdefault(canonical_address, address)

        if not canonical_to_original:
            return prices_accumulator

        canonical_to_symbol = {
            canonical: symbol
            for canonical, symbol in (
                (canonical, self._symbol_for(canonical))
                for canonical in canonical_to_original
            )
            if symbol
        }
        unknown_addresses = set(canonical_to_original) - set(canonical_to_symbol)
        for canonical in unknown_addresses:
            logger.warning(
                "Address %s not recognized in adapter configuration, skipping",
                canonical_to_original[canonical],
            )

        symbols = list(canonical_to_symbol.values())
        feed_ids = await asyncio.gather(
            *(self._resolve_feed_id(sym, "USD") for sym in symbols)
        )
        resolved_assets: dict[str, tuple[str, str, str]] = {}
        for canonical, symbol, feed_id in zip(
            canonical_to_symbol.keys(), symbols, feed_ids
        ):
            if feed_id:
                resolved_assets[canonical] = (
                    canonical_to_original[canonical],
                    symbol,
                    feed_id,
                )
            else:
                logger.warning("Could not resolve feed ID for %s/USD, skipping", symbol)

        if not resolved_assets:
            return prices_accumulator

        all_feed_ids = [base_feed_id] + [data[2] for data in resolved_assets.values()]
        query_string = urlencode([("ids[]", feed_id) for feed_id in all_feed_ids])
        url = f"{self.hermes_endpoint}/v2/updates/price/latest?{query_string}"

        response = await self._http_get(url)
        response.raise_for_status()
        parsed_feeds = response.json().get("parsed", [])
        feeds_by_id = {feed.get("id"): feed for feed in parsed_feeds}
        logger.debug("Received %d price feeds", len(parsed_feeds))

        base_feed = feeds_by_id.get(base_feed_id.removeprefix("0x"))
        if not base_feed:
            raise ValueError(f"{base_symbol}/USD price feed not in Pyth response")

        base_price_obj = base_feed.get("price", {}) or {}
        base_publish_time = int(base_price_obj.get("publish_time", 0))
        now = int(time.time())
        if (now - base_publish_time) > self.staleness_threshold:
            raise ValueError(
                f"{base_symbol}/USD price is stale (age: {now - base_publish_time}s)"
            )

        base_usd_price_18 = self._scale_to_18(
            int(base_price_obj.get("price", 0)), int(base_price_obj.get("expo", 0))
        )
        self._check_confidence(base_price_obj, base_usd_price_18, f"{base_symbol}/USD")
        logger.debug("%s/USD price: $%.6f", base_symbol, base_usd_price_18 / 10**18)

        for original_address, symbol, feed_id in resolved_assets.values():
            feed = feeds_by_id.get(feed_id.removeprefix("0x"))
            if not feed:
                logger.warning("Price feed for %s/USD not found", symbol)
                continue

            price_obj = feed.get("price", {}) or {}
            publish_time = int(price_obj.get("publish_time", 0))
            if (now - publish_time) > self.staleness_threshold:
                logger.warning(
                    "%s/USD price is stale (age: %ss), skipping",
                    symbol,
                    now - publish_time,
                )
                continue

            asset_usd_price_18 = self._scale_to_18(
                int(price_obj.get("price", 0)), int(price_obj.get("expo", 0))
            )
            self._check_confidence(price_obj, asset_usd_price_18, f"{symbol}/USD")

            asset_price_18 = (asset_usd_price_18 * 10**18) // base_usd_price_18
            prices_accumulator.prices[original_address] = asset_price_18
            logger.debug(
                "%s: $%.6f = %s %s",
                symbol,
                asset_usd_price_18 / 10**18,
                asset_price_18,
                base_symbol,
            )

        self.validate_prices(prices_accumulator)
        return prices_accumulator
