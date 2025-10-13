from __future__ import annotations

from .chainlink import ChainlinkAdapter
from .wsteth import WstETHAdapter

PRICE_ADAPTERS = [
    ChainlinkAdapter,
    WstETHAdapter,
]

__all__ = ["PRICE_ADAPTERS", "ChainlinkAdapter", "WstETHAdapter"]
