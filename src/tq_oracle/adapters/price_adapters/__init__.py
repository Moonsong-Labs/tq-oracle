from __future__ import annotations

from .cow_swap import CowSwapAdapter
from .eth import ETHAdapter

PRICE_ADAPTERS = [
    CowSwapAdapter,
    ETHAdapter,
]

__all__ = ["PRICE_ADAPTERS", "CowSwapAdapter", "ETHAdapter"]
