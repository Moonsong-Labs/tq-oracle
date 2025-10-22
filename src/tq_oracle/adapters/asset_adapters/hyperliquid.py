from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hyperliquid.info import Info

from ...constants import (
    HL_MAINNET_API_URL,
    HL_TESTNET_API_URL,
    USDC_MAINNET,
    USDC_SEPOLIA,
)
from ...logger import get_logger
from .base import AssetData, BaseAssetAdapter, AdapterChain

if TYPE_CHECKING:
    from ...config import OracleCLIConfig

logger = get_logger(__name__)


class HyperliquidAdapter(BaseAssetAdapter):
    """Adapter for querying Hyperliquid protocol assets."""

    def __init__(self, config: OracleCLIConfig, chain: str = "hyperliquid"):
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
        """Fetch asset data from Hyperliquid for the given vault.

        Args:
            subvault_address: The subvault contract address to query (used as fallback if config doesn't specify hl_subvault_address)

        Returns:
            Account portfolio value as USDC asset
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
            logger.debug("Calling portfolio API to fetch TWAP data...")
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
                logger.warning(
                    "Empty account history for %s, returning 0", address_to_query
                )
                return []

            values = []
            for timestamp, value_str in account_history:
                try:
                    values.append(float(value_str))
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Invalid value at timestamp %s: %s (error: %s)",
                        timestamp,
                        value_str,
                        e,
                    )

            if not values:
                logger.warning("No valid values in account history, returning 0")
                return []

            twap = sum(values) / len(values)
            logger.info(
                "TWAP over %d hourly snapshots: $%.2f (min: $%.2f, max: $%.2f)",
                len(values),
                twap,
                min(values),
                max(values),
            )

            amount_native = int(twap * 1e18)
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
