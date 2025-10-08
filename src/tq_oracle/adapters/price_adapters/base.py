from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol


@dataclass
class PriceData:
    """Price data from a price adapter."""

    base_asset: str
    prices: dict[str, int]  # asset_address -> price_wei (18 decimals)


class PriceAdapter(Protocol):
    """Protocol defining the interface for price adapters."""

    @property
    def adapter_name(self) -> str:
        """Return the name of this adapter."""
        ...

    async def fetch_prices(self, asset_addresses: list[str]) -> PriceData:
        """Fetch prices for the given asset addresses.

        Args:
            asset_addresses: List of asset contract addresses to get prices for

        Returns:
            List of price data for the assets
        """
        ...


class BasePriceAdapter(ABC):
    """Abstract base class for price adapters."""

    def __init__(self, config: object):
        """Initialize the adapter with configuration."""
        self.config = config

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return the name of this adapter."""
        ...

    @abstractmethod
    async def fetch_prices(self, asset_addresses: list[str]) -> PriceData:
        """Fetch prices for the given asset addresses."""
        ...
