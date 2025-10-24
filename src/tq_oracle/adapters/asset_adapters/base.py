from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from ...settings import OracleSettings


class AdapterChain(Enum):
    """Enum indicating which blockchain/RPC an adapter uses."""

    VAULT_CHAIN = "vault_chain"  # Main vault network (uses vault_rpc)
    HYPERLIQUID = "hyperliquid"  # Hyperliquid chain (uses hl_rpc)


@dataclass
class AssetData:
    """Raw asset data from a protocol adapter."""

    asset_address: str
    amount: int  # in native units


class BaseAssetAdapter(ABC):
    """Abstract base class for asset adapters."""

    def __init__(self, config: OracleSettings, chain: str = "vault_chain"):
        """Initialize the adapter with configuration.

        Args:
            config: Oracle configuration
            chain: Which chain to operate on - "vault_chain" or "hyperliquid"
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
