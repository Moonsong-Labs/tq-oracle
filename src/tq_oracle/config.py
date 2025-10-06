from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class OracleCLIConfig:
    vault_address: str
    oracle_helper_address: str
    destination: str
    mainnet_rpc: str
    testnet_rpc: str
    hl_rpc: Optional[str]
    testnet: bool
    dry_run: bool
    backoff: bool
    private_key: Optional[str]

    def as_safe_dict(self) -> dict[str, object]:
        """Return the config as a dict with secrets redacted."""
        data = asdict(self)
        if self.private_key:
            data["private_key"] = "***redacted***"
        return data
