from __future__ import annotations

from .chainlink import ChainlinkAdapter
from .cow_swap import CowSwapAdapter
from .wsteth import WstETHAdapter

PRICE_ADAPTERS = [
    ChainlinkAdapter,
    CowSwapAdapter,
    WstETHAdapter,
]

__all__ = ["PRICE_ADAPTERS", "ChainlinkAdapter", "CowSwapAdapter", "WstETHAdapter"]
