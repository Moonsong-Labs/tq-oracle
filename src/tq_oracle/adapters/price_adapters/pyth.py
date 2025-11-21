from __future__ import annotations

import asyncio
import json
import logging
import time
from urllib.parse import urlencode

import backoff
import requests
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from web3 import Web3

from tq_oracle.abi import load_erc20_abi
from tq_oracle.constants import PYTH_PRICE_FEED_IDS
from tq_oracle.settings import OracleSettings

from .base import BasePriceAdapter, PriceData

logger = logging.getLogger(__name__)


class HermesPrice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    price: int
    expo: int
    publish_time: int
    conf: int = 0

    @field_validator("price", "expo", "publish_time", "conf", mode="before")
    @classmethod
    def _ints_from_str(cls, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError("value must be an integer")


class HermesFeed(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    price: HermesPrice

    @field_validator("id", mode="before")
    @classmethod
    def _non_empty_id(cls, value) -> str:
        if value is None:
            raise ValueError("feed id must be non-empty")
        as_str = str(value)
        if not as_str:
            raise ValueError("feed id must be non-empty")
        return as_str


class HermesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    parsed: list[HermesFeed]


class PythAdapter(BasePriceAdapter):
    """Adapter for querying Pyth Network price feeds."""

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.hermes_endpoint = config.pyth_hermes_endpoint
        self.staleness_threshold = config.pyth_staleness_threshold
        self.max_confidence_ratio = config.pyth_max_confidence_ratio
        self.vault_rpc = config.vault_rpc_required
        self.last_missing_feeds: set[str] = set()
        self.last_stale_feeds: set[str] = set()

        self._address_to_symbol: dict[str, str] = {
            Web3.to_checksum_address(addr): sym
            for sym, addr in config.assets.items()
            if isinstance(addr, str) and addr
        }
        self._feed_ids: dict[str, str] = {}

    @property
    def adapter_name(self) -> str:
        return "pyth"

    def _scale_to_18(self, value: int, expo: int) -> int:
        """Scale an integer `value * 10**expo` to 18-decimal fixed point."""
        shift = 18 + expo
        return value * (10**shift) if shift >= 0 else value // (10**-shift)

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, requests.exceptions.HTTPError),
        max_tries=5,
        giveup=lambda e: (
            isinstance(e, requests.exceptions.HTTPError)
            and e.response is not None
            and e.response.status_code not in {429, 500, 502, 503, 504}
        ),
        jitter=backoff.full_jitter,
    )
    async def _http_get(self, url: str, *, params: dict | None = None):
        response = await asyncio.to_thread(
            lambda: requests.get(url, params=params, timeout=2.0)
        )
        response.raise_for_status()
        return response

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
        except requests.RequestException as exc:  # pragma: no cover
            logger.error(
                "Network error discovering feed for %s/%s: %s", symbol, quote, exc
            )
            return None

        try:
            feeds = r.json()
        except (json.JSONDecodeError, ValueError) as exc:  # pragma: no cover
            logger.error(
                "Invalid JSON in feed discovery response for %s/%s: %s",
                symbol,
                quote,
                exc,
            )
            return None
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

    def _check_confidence(
        self, price_obj: HermesPrice, price_18: int, symbol: str
    ) -> None:
        conf_18 = self._scale_to_18(price_obj.conf, price_obj.expo)
        denom = abs(price_18)
        if denom == 0:
            raise ValueError(f"{symbol} price is zero")
        conf_ratio = conf_18 / denom
        if conf_ratio > self.max_confidence_ratio:
            raise ValueError(
                f"{symbol} confidence ratio {conf_ratio:.4f} exceeds maximum {self.max_confidence_ratio}"
            )

    def _symbol_for(self, address: str) -> str | None:
        return self._address_to_symbol.get(Web3.to_checksum_address(address))

    async def get_token_decimals(self, token_address: str) -> int:
        """Fetch token decimals from chain with caching."""

        w3 = Web3(Web3.HTTPProvider(self.vault_rpc))
        erc20_abi = load_erc20_abi()
        token_contract = w3.eth.contract(
            address=w3.to_checksum_address(token_address),
            abi=erc20_abi,
        )

        decimals = await asyncio.to_thread(
            lambda: int(
                token_contract.functions.decimals().call(
                    block_identifier=self.config.block_number_required
                )
            )
        )

        return decimals

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        self.last_missing_feeds = set()
        self.last_stale_feeds = set()

        base_address = Web3.to_checksum_address(prices_accumulator.base_asset)
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
            canonical_address = Web3.to_checksum_address(address)
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
                self.last_missing_feeds.add(canonical_to_original[canonical])

        if not resolved_assets:
            return prices_accumulator

        all_feed_ids = [base_feed_id] + [data[2] for data in resolved_assets.values()]
        query_string = urlencode([("ids[]", feed_id) for feed_id in all_feed_ids])
        url = f"{self.hermes_endpoint}/v2/updates/price/latest?{query_string}"

        response = await self._http_get(url)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Pyth Hermes: {e}")

        if not isinstance(data, dict):
            raise ValueError(f"Expected dict from Pyth, got {type(data).__name__}")

        if "parsed" not in data:
            raise ValueError("Missing 'parsed' field in Pyth response")

        parsed_feeds = data["parsed"]
        if not isinstance(parsed_feeds, list):
            raise ValueError(
                f"Expected list for 'parsed' field, got {type(parsed_feeds).__name__}"
            )

        for i, feed in enumerate(parsed_feeds):
            if not isinstance(feed, dict):
                raise ValueError(
                    f"Invalid feed item at index {i}: expected dict, got {type(feed).__name__}"
                )

        try:
            parsed_response = HermesResponse.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"Invalid Pyth Hermes response: {e}") from e

        feeds_by_id = {feed.id: feed for feed in parsed_response.parsed}
        logger.debug("Received %d price feeds", len(parsed_response.parsed))

        base_feed = feeds_by_id.get(base_feed_id.removeprefix("0x"))
        if not base_feed:
            raise ValueError(f"{base_symbol}/USD price feed not in Pyth response")

        base_price_obj = base_feed.price
        base_publish_time = base_price_obj.publish_time
        now = int(time.time())
        if (now - base_publish_time) > self.staleness_threshold:
            raise ValueError(
                f"{base_symbol}/USD price is stale (age: {now - base_publish_time}s)"
            )

        base_usd_price_18 = self._scale_to_18(base_price_obj.price, base_price_obj.expo)
        self._check_confidence(base_price_obj, base_usd_price_18, f"{base_symbol}/USD")
        logger.debug("%s/USD price: $%.6f", base_symbol, base_usd_price_18 / 10**18)

        for original_address, symbol, feed_id in resolved_assets.values():
            feed = feeds_by_id.get(feed_id.removeprefix("0x"))
            if not feed:
                logger.warning("Price feed for %s/USD not found", symbol)
                self.last_missing_feeds.add(original_address)
                continue

            price_obj = feed.price
            publish_time = price_obj.publish_time
            if (now - publish_time) > self.staleness_threshold:
                logger.warning(
                    "%s/USD price is stale (age: %ss), skipping",
                    symbol,
                    now - publish_time,
                )
                self.last_stale_feeds.add(original_address)
                continue

            asset_usd_price_18 = self._scale_to_18(price_obj.price, price_obj.expo)
            self._check_confidence(price_obj, asset_usd_price_18, f"{symbol}/USD")

            asset_price_18 = (asset_usd_price_18 * 10**18) // base_usd_price_18
            decimals = await self.get_token_decimals(original_address)
            price_per_base_unit_d18 = (asset_price_18 * 10**18) // (10**decimals)
            prices_accumulator.prices[original_address] = price_per_base_unit_d18
            logger.debug(
                "%s: $%.6f = %.9f %s per base unit (decimals=%d)",
                symbol,
                asset_usd_price_18 / 10**18,
                price_per_base_unit_d18 / 10**18,
                base_symbol,
                decimals,
            )

        self.validate_prices(prices_accumulator)
        return prices_accumulator
