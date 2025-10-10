from __future__ import annotations

from .hyperliquid import HyperliquidAdapter
from .idle_balances import IdleBalancesAdapter

ASSET_ADAPTERS = [
    HyperliquidAdapter,
    IdleBalancesAdapter,
]

__all__ = ["ASSET_ADAPTERS", "HyperliquidAdapter", "IdleBalancesAdapter"]
