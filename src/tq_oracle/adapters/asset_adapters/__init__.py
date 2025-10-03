from __future__ import annotations

from .hyperliquid import HyperliquidAdapter

ASSET_ADAPTERS = [
    HyperliquidAdapter,
]

__all__ = ["ASSET_ADAPTERS", "HyperliquidAdapter"]
