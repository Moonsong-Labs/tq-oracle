from __future__ import annotations

from .base import BaseAssetAdapter
from .hyperliquid import HyperliquidAdapter
from .idle_balances import IdleBalancesAdapter
from .streth import StrETHAdapter
from .base import BaseAssetAdapter

ADAPTER_REGISTRY: dict[str, type[BaseAssetAdapter]] = {
    "idle_balances": IdleBalancesAdapter,
    "hyperliquid": HyperliquidAdapter,
    "streth": StrETHAdapter
}

ASSET_ADAPTERS: list[type[BaseAssetAdapter]] = list(ADAPTER_REGISTRY.values())


def get_adapter_class(adapter_name: str) -> type[BaseAssetAdapter]:
    """Get adapter class by name.

    Args:
        adapter_name: Name of the adapter (case-insensitive)

    Returns:
        Adapter class

    Raises:
        ValueError: If adapter_name is not recognized
    """
    adapter_name_normalized = adapter_name.lower()
    if adapter_name_normalized not in ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown adapter '{adapter_name}'. "
            f"Available: {', '.join(ADAPTER_REGISTRY.keys())}"
        )
    return ADAPTER_REGISTRY[adapter_name_normalized]


__all__ = [
    "ASSET_ADAPTERS",
    "ADAPTER_REGISTRY",
    "HyperliquidAdapter",
    "IdleBalancesAdapter",
    "StrETHAdapter"
    "get_adapter_class",
]
