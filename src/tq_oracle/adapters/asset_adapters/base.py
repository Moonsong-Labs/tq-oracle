from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from ...config import OracleCLIConfig


class AdapterChain(Enum):
    """Enum indicating which blockchain/RPC an adapter uses."""

    L1 = "l1"  # Ethereum L1 (uses l1_rpc)
    HYPERLIQUID = "hyperliquid"  # Hyperliquid chain (uses hl_rpc)


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

    @property
    def chain(self) -> AdapterChain:
        """Return which chain this adapter operates on."""
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

    def __init__(self, config: OracleCLIConfig, chain: str = "l1"):
        """Initialize the adapter with configuration.

        Args:
            config: Oracle configuration
            chain: Which chain to operate on - "l1" or "hyperliquid"
        """
        self.config = config
        self._chain = chain

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return the name of this adapter."""
        ...

    @property
    @abstractmethod
    def chain(self) -> AdapterChain:
        """Return which chain this adapter operates on."""
        ...

    @abstractmethod
    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        """Fetch asset data for the given subvault."""
        ...
