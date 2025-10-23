from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from eth_typing import URI
from web3 import Web3

from .constants import NetworkAssets


class Network(str, Enum):
    MAINNET = "mainnet"
    SEPOLIA = "sepolia"
    BASE = "base"


@dataclass
class SubvaultAdapterConfig:
    """Configuration for additional adapters on a specific subvault."""

    subvault_address: str
    chain: str = "l1"  # Which chain this subvault is on: "l1" or "hyperliquid"
    additional_adapters: list[str] = field(default_factory=list)
    skip_idle_balances: bool = False
    skip_subvault_existence_check: bool = False


@dataclass
class OracleCLIConfig:
    vault_address: Optional[str] = None
    oracle_helper_address: Optional[str] = None
    l1_rpc: Optional[str] = None
    l1_subvault_address: Optional[str] = None
    safe_address: Optional[str] = None
    network: Network = Network.MAINNET
    hl_rpc: Optional[str] = None
    hl_subvault_address: Optional[str] = None
    testnet: bool = False
    dry_run: bool = True
    safe_txn_srvc_api_key: Optional[str] = None
    private_key: Optional[str] = None
    ignore_empty_vault: bool = False
    ignore_timeout_check: bool = False
    ignore_active_proposal_check: bool = False
    using_default_rpc: bool = False
    pre_check_retries: int = 3
    pre_check_timeout: float = 10.0
    _chain_id: Optional[int] = None
    _oracle_address: Optional[str] = None
    max_calls: int = 3
    rpc_max_concurrent_calls: int = 5
    rpc_delay: float = 0.15
    rpc_jitter: float = 0.10
    chainlink_price_warning_tolerance_percentage: float = 0.5
    chainlink_price_failure_tolerance_percentage: float = 1.0
    log_level: str = "INFO"
    subvault_adapters: list[SubvaultAdapterConfig] = field(default_factory=list)

    @property
    def chain_id(self) -> int:
        """Derive chain ID from the RPC endpoint."""
        if self._chain_id is None:
            if not self.l1_rpc:
                raise ValueError("l1_rpc must be set before accessing chain_id")
            w3 = Web3(
                Web3.HTTPProvider(URI(self.l1_rpc), request_kwargs={"timeout": 15})
            )
            if not w3.is_connected():
                raise ConnectionError(f"Failed to connect to RPC: {self.l1_rpc}")
            self._chain_id = w3.eth.chain_id
        return self._chain_id

    @property
    def oracle_address(self) -> str:
        """Fetch oracle address from the vault contract."""
        if self._oracle_address is None:
            if not self.vault_address or not self.l1_rpc:
                raise ValueError(
                    "vault_address and l1_rpc must be set before accessing oracle_address"
                )
            from .abi import get_oracle_address_from_vault

            self._oracle_address = get_oracle_address_from_vault(
                self.vault_address, self.l1_rpc
            )
        return self._oracle_address

    @property
    def is_broadcast(self) -> bool:
        """Check if Broadcast mode is enabled (Safe address provided and not dry-run)."""
        return self.safe_address is not None and not self.dry_run

    @property
    def vault_address_required(self) -> str:
        """Get vault_address, raising ValueError if not set."""
        if self.vault_address is None:
            raise ValueError("vault_address must be configured")
        return self.vault_address

    @property
    def l1_rpc_required(self) -> str:
        """Get l1_rpc, raising ValueError if not set."""
        if self.l1_rpc is None:
            raise ValueError("l1_rpc must be configured")
        return self.l1_rpc

    @property
    def assets(self) -> NetworkAssets:
        """Get the assets for the configured network.

        Returns:
            NetworkAssets for the configured network
        """
        from .constants import ETH_MAINNET_ASSETS, SEPOLIA_ASSETS, BASE_ASSETS

        network_assets_map = {
            Network.MAINNET: ETH_MAINNET_ASSETS,
            Network.SEPOLIA: SEPOLIA_ASSETS,
            Network.BASE: BASE_ASSETS,
        }

        if self.network not in network_assets_map:
            raise ValueError(f"Unknown network: {self.network}")

        return network_assets_map[self.network]

    def get_subvault_config(self, subvault_address: str) -> SubvaultAdapterConfig:
        """Get adapter configuration for a specific subvault.

        Args:
            subvault_address: The subvault address to look up

        Returns:
            SubvaultAdapterConfig for this subvault, or default config if not configured
        """
        normalized_address = subvault_address.lower()
        for config in self.subvault_adapters:
            if config.subvault_address.lower() == normalized_address:
                return config
        # Return default config: L1 chain, no additional adapters, don't skip idle_balances
        return SubvaultAdapterConfig(
            subvault_address=subvault_address,
            chain="l1",
            additional_adapters=[],
            skip_idle_balances=False,
        )

    def as_safe_dict(self) -> dict[str, object]:
        """Return the config as a dict with secrets redacted."""
        data = asdict(self)
        if self.private_key:
            data["private_key"] = "***redacted***"
        if self.safe_txn_srvc_api_key:
            data["safe_txn_srvc_api_key"] = "***redacted***"
        return data
