from __future__ import annotations

from .hyperliquid import HyperliquidAdapter

# Registry of asset adapters that fetch assets from protocols
# These will be executed in parallel during the fork stage
ASSET_ADAPTERS = [
    HyperliquidAdapter,
    # Add new asset adapters here as they're implemented
    # Example: AaveAdapter, UniV3Adapter, SubvaultAdapter, etc.
]

__all__ = ["ASSET_ADAPTERS", "HyperliquidAdapter"]
