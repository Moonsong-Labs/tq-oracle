from __future__ import annotations

from .chainlink import ChainlinkAdapter
from .cow_swap import CowSwapAdapter
from .eth import ETHAdapter

PRICE_ADAPTERS = [
    CowSwapAdapter,
    ETHAdapter,
]

__all__ = ["PRICE_ADAPTERS", "ChainlinkAdapter", "CowSwapAdapter", "ETHAdapter"]
