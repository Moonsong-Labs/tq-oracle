from __future__ import annotations

import asyncio
import importlib
import importlib.util
import math
import time
from typing import Any, Literal, Optional

from ...constants import (
    HL_MAINNET_API_URL,
    HL_MAX_PORTFOLIO_STALENESS_SECONDS,
    HL_TESTNET_API_URL,
    USDC_HL_MAINNET,
    USDC_HL_TESTNET,
)
from ...logger import get_logger
from ...settings import OracleSettings
from .base import AdapterChain, AssetData, BaseAssetAdapter

logger = get_logger(__name__)

module_spec = importlib.util.find_spec("hyperliquid.info")
if module_spec is not None:
    Info = getattr(importlib.import_module("hyperliquid.info"), "Info", None)
else:  # pragma: no cover - dependency optional
    Info = None

HyperliquidEnv = Literal["mainnet", "testnet"]
HyperliquidInfo = Any


class HyperliquidAdapter(BaseAssetAdapter):
    """Hyperliquid asset adapter.

    Derives NAV from the latest timestamped portfolio value returned
    by the portfolio endpoint.

    Rejects stale portfolio values older than HL_MAX_PORTFOLIO_STALENESS_SECONDS.
    Raises ValueError on empty/invalid history or stale portfolio values.
    """

    usdc_address: str
    api_url: str
    _environment: str

    def __init__(self, config: OracleSettings, chain: str = "hyperliquid"):
        """Initialize the Hyperliquid adapter.

        Args:
            config: Oracle configuration
            chain: Which chain to operate on (defaults to "hyperliquid")
        """
        super().__init__(config, chain=chain)
        info_cls = Info
        if info_cls is None:
            raise RuntimeError(
                "Hyperliquid integration requires hyperliquid-python-sdk. Install the dependency before enabling support."
            )
        self._info_cls = info_cls

        resolved_env: HyperliquidEnv = (
            getattr(config, "hyperliquid_env", None) or "mainnet"
        )
        self._environment: HyperliquidEnv = resolved_env

        assets = config.assets
        usdc_address = assets["USDC"]
        if usdc_address is None:
            raise ValueError("USDC address is required for Hyperliquid adapter")
        self.usdc_address = usdc_address
        resolved_api_url = getattr(config, "hyperliquid_api_url", None)
        if resolved_api_url is None:
            resolved_api_url = (
                HL_TESTNET_API_URL
                if self._environment == "testnet"
                else HL_MAINNET_API_URL
            )
        self.api_url = resolved_api_url
        resolved_hl_usdc = getattr(config, "hyperliquid_usdc_address", None)
        if resolved_hl_usdc is None:
            resolved_hl_usdc = (
                USDC_HL_TESTNET if self._environment == "testnet" else USDC_HL_MAINNET
            )
        self._hl_usdc_address = resolved_hl_usdc

    @property
    def adapter_name(self) -> str:
        return "hyperliquid"

    @property
    def chain(self) -> AdapterChain:
        return AdapterChain.HYPERLIQUID

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch current portfolio value (NAV) for the given subvault.

        Selects the most recent valid point from accountValueHistory
        and returns it as a USDC AssetData scaled to 18 decimals.

        Args:
            subvault_address: Subvault address to query (overridden by
                config.hl_subvault_address if set).

        Returns:
            list[AssetData]: Single USDC asset with amount set to the latest NAV
            scaled to 1e18.

        Raises:
            ValueError: If the 'day' period is missing, the history is empty,
                no valid numeric values can be parsed, or if the latest value
                is stale (older than HL_MAX_PORTFOLIO_STALENESS_SECONDS).
        """
        # Use config's hl_subvault_address if set, otherwise fall back to passed address
        hl_subvault_address = getattr(self.config, "hl_subvault_address", None)
        address_to_query = hl_subvault_address or subvault_address

        logger.info(
            "Fetching Hyperliquid assets for %s (env=%s)",
            address_to_query,
            self._environment,
        )
        logger.debug("Using API URL: %s", self.api_url)

        info_cls = getattr(self, "_info_cls", None)
        if info_cls is None:
            raise RuntimeError("Hyperliquid integration is disabled.")
        info = await asyncio.to_thread(info_cls, base_url=self.api_url, skip_ws=True)

        try:
            logger.debug("Calling portfolio API to fetch latest NAV data...")
            portfolio_data = await asyncio.to_thread(
                info.portfolio, user=address_to_query
            )

            day_data = next(
                (item[1] for item in portfolio_data if item[0] == "day"), None
            )
            if not day_data:
                raise ValueError("No 'day' period data in portfolio response")

            account_history = day_data.get("accountValueHistory", [])
            if not account_history:
                logger.warning("Empty account history for %s", address_to_query)
                raise ValueError("Hyperliquid: empty account history")

            # Normalize, filter invalid entries, and sort by timestamp ascending
            def _parse_point(ts: Any, value_str: Any) -> Optional[tuple[int, float]]:
                try:
                    ts_ms = int(ts)
                    x = float(value_str)
                    if math.isfinite(x):
                        return ts_ms, x
                except Exception as e:
                    logger.debug(
                        "Skipping invalid point (%s, %s): %s", ts, value_str, e
                    )
                return None

            clean: list[tuple[int, float]] = [
                point
                for point in (
                    _parse_point(ts, value_str) for ts, value_str in account_history
                )
                if point is not None
            ]

            if not clean:
                logger.warning(
                    "No valid numeric values in account history for %s",
                    address_to_query,
                )
                raise ValueError("Hyperliquid: no valid latest value")

            clean.sort(key=lambda p: p[0])
            last_ts_ms, latest_value = clean[-1]

            # Reject stale portfolio values
            now_ms = int(time.time() * 1000)
            max_staleness_ms = HL_MAX_PORTFOLIO_STALENESS_SECONDS * 1000
            age_ms = now_ms - last_ts_ms
            if age_ms > max_staleness_ms:
                msg = (
                    f"Hyperliquid: stale portfolio value; "
                    f"age={age_ms / 1000:.1f}s exceeds {max_staleness_ms / 1000:.0f}s"
                )
                logger.error(msg)
                raise ValueError(msg)

            logger.info(
                "Hyperliquid latest NAV: $%.2f (age=%.1fs)",
                latest_value,
                max(0, age_ms) / 1000.0,
            )

            amount_native = int(latest_value * 1e18)

            logger.debug("Using USDC address: %s", self.usdc_address)
            logger.debug("Native amount: %d", amount_native)

            return [
                AssetData(
                    asset_address=self.usdc_address,
                    amount=amount_native,
                )
            ]
        except Exception as e:
            logger.error("Failed to fetch Hyperliquid assets: %s", e)
            raise
