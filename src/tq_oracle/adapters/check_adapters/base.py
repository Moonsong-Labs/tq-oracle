"""Base class for check adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CheckResult:
    """Result from a check adapter."""

    passed: bool
    message: str
    retry_recommended: bool = False


class BaseCheckAdapter(ABC):
    """Base class for all check adapters."""

    def __init__(self, config: object):
        """Initialize the adapter with configuration."""
        self.config = config

    @abstractmethod
    async def run_check(self) -> CheckResult:
        """Execute the check and return result."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this check."""
        pass
