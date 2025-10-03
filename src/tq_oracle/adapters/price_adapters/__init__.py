from __future__ import annotations

from .chainlink import ChainlinkAdapter

PRICE_ADAPTERS = [
    ChainlinkAdapter,
]

__all__ = ["PRICE_ADAPTERS", "ChainlinkAdapter"]
