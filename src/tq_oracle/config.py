from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from eth_typing import URI
from web3 import Web3


@dataclass
class OracleCLIConfig:
    vault_address: str
    oracle_helper_address: str
    l1_rpc: str
    safe_address: Optional[str]
    hl_rpc: Optional[str]
    hl_subvault_address: Optional[str]
    testnet: bool
    dry_run: bool
    safe_txn_srvc_api_key: Optional[str]
    private_key: Optional[str]
    ignore_empty_vault: bool = False
    _chain_id: Optional[int] = None
    _oracle_address: Optional[str] = None

    @property
    def chain_id(self) -> int:
        """Derive chain ID from the RPC endpoint."""
        if self._chain_id is None:
            w3 = Web3(Web3.HTTPProvider(URI(self.l1_rpc)))
            if not w3.is_connected():
                raise ConnectionError(f"Failed to connect to RPC: {self.l1_rpc}")
            self._chain_id = w3.eth.chain_id
        return self._chain_id

    @property
    def oracle_address(self) -> str:
        """Fetch oracle address from the vault contract."""
        if self._oracle_address is None:
            from .abi import get_oracle_address_from_vault

            self._oracle_address = get_oracle_address_from_vault(
                self.vault_address, self.l1_rpc
            )
        return self._oracle_address

    @property
    def is_broadcast(self) -> bool:
        """Check if Broadcast mode is enabled (Safe address provided and not dry-run)."""
        return self.safe_address is not None and not self.dry_run

    def as_safe_dict(self) -> dict[str, object]:
        """Return the config as a dict with secrets redacted."""
        data = asdict(self)
        if self.private_key:
            data["private_key"] = "***redacted***"
        if self.safe_txn_srvc_api_key:
            data["safe_txn_srvc_api_key"] = "***redacted***"
        return data
