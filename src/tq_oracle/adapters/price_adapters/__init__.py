from __future__ import annotations

from .chainlink import ChainlinkAdapter

# Registry of price adapters that fetch prices for assets
# These run after asset aggregation to price the discovered assets
PRICE_ADAPTERS = [
    ChainlinkAdapter,
    # Add new price adapters here as they're implemented
    # Example: PythAdapter, UniswapV3TWAPAdapter, etc.
]

__all__ = ["PRICE_ADAPTERS", "ChainlinkAdapter"]
