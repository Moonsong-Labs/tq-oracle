from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class OracleCLIConfig:
    vault_address: str
    oracle_address: str
    mainnet_rpc: str
    safe_address: Optional[str]
    chain_id: int
    hl_rpc: Optional[str]
    testnet: bool
    dry_run: bool
    backoff: bool
    safe_txn_srvc_api_key: Optional[str]
    private_key: Optional[str]

    @property
    def is_broadcast(self) -> bool:
        """Check if Broadcast mode is enabled (Safe address provided and not dry-run)."""
        return self.safe_address is not None and not self.dry_run

    def as_safe_dict(self) -> dict[str, object]:
        """Return the config as a dict with secrets redacted."""
        data = asdict(self)
        if self.private_key:
            data["private_key"] = "***redacted***"
        data.pop("safe_txn_srvc_api_key", None)
        return data
