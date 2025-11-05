from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ...settings import OracleSettings


@dataclass
class AssetData:
    """Raw asset data from a protocol adapter."""

    asset_address: str
    amount: int  # in native units


class BaseAssetAdapter(ABC):
    """Abstract base class for asset adapters."""

    def __init__(self, config: OracleSettings):
        """Initialize the adapter with configuration.

        Args:
            config: Oracle configuration
        """
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
