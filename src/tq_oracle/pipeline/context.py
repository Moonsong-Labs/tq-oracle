from __future__ import annotations

from dataclasses import dataclass

from ..state import AppState


@dataclass
class PipelineContext:
    state: AppState
    vault_address: str
