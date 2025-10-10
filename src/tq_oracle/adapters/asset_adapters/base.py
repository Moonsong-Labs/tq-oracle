from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol
from ...config import OracleCLIConfig


@dataclass
class AssetData:
    """Raw asset data from a protocol adapter."""

    asset_address: str
    amount: int  # in native units


class AssetAdapter(Protocol):
    """Protocol defining the interface for asset adapters."""

    @property
    def adapter_name(self) -> str:
        """Return the name of this adapter."""
        ...

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch asset data for the given vault.

        Args:
            subvault_address: The subvault contract address to query

        Returns:
            List of asset data from this protocol
        """
        ...


class BaseAssetAdapter(ABC):
    """Abstract base class for asset adapters."""

    def __init__(self, config: OracleCLIConfig):
        """Initialize the adapter with configuration."""
        self.config = config

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return the name of this adapter."""
        ...

    @abstractmethod
    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch asset data for the given subvault."""
        ...
