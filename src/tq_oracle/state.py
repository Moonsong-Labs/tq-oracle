"""Application state container."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .settings import OracleSettings


@dataclass
class AppState:
    """Container for application-wide state and dependencies.

    Passed through the pipeline to avoid global state and enable testing.
    """

    settings: OracleSettings
    logger: logging.Logger
