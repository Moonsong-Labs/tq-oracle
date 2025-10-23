"""Domain models for the oracle."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    """Represents an asset with its address, amount, and decimals."""

    address: str
    amount: int
    token_decimals: int


@dataclass(frozen=True)
class PricedAsset:
    """Represents an asset with its price in USD."""

    asset: Asset
    price_usd: float


@dataclass(frozen=True)
class TvlReport:
    """Represents a TVL report for a vault."""

    vault_address: str
    total_usd: float
    items: list[PricedAsset]
