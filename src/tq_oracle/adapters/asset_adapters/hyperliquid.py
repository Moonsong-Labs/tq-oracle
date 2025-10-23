from __future__ import annotations

import asyncio
import time
import math
from typing import TYPE_CHECKING, Optional, Any

from hyperliquid.info import Info

from ...constants import (
    HL_MAINNET_API_URL,
    HL_TESTNET_API_URL,
    USDC_MAINNET,
    USDC_SEPOLIA,
    HL_MAX_PORTFOLIO_STALENESS_SECONDS,
)
from ...logger import get_logger
from .base import AssetData, BaseAssetAdapter, AdapterChain

if TYPE_CHECKING:
    from ...settings import OracleSettings

logger = get_logger(__name__)


class HyperliquidAdapter(BaseAssetAdapter):
    """Hyperliquid asset adapter.

    Derives NAV from the latest timestamped portfolio value returned
    by the portfolio endpoint.

    Rejects stale portfolio values older than HL_MAX_PORTFOLIO_STALENESS_SECONDS.
    Raises ValueError on empty/invalid history or stale portfolio values.
    """

    def __init__(self, config: OracleSettings, chain: str = "hyperliquid"):
        """Initialize the Hyperliquid adapter.

        Args:
            config: Oracle configuration
            chain: Which chain to operate on (defaults to "hyperliquid")
        """
        super().__init__(config, chain=chain)
        self.testnet = config.testnet

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
        address_to_query = self.config.hl_subvault_address or subvault_address

        base_url = HL_TESTNET_API_URL if self.testnet else HL_MAINNET_API_URL
        logger.info(
            "Fetching Hyperliquid assets for %s (testnet=%s)",
            address_to_query,
            self.testnet,
        )
        logger.debug("Using API URL: %s", base_url)

        info = await asyncio.to_thread(Info, base_url=base_url, skip_ws=True)

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
            usdc_address = USDC_SEPOLIA if self.testnet else USDC_MAINNET

            logger.debug("Using USDC address: %s", usdc_address)
            logger.debug("Native amount: %d", amount_native)

            return [
                AssetData(
                    asset_address=usdc_address,
                    amount=amount_native,
                )
            ]
        except Exception as e:
            logger.error("Failed to fetch Hyperliquid assets: %s", e)
            raise
