from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from tq_oracle.adapters.check_adapters.base import CheckResult

if TYPE_CHECKING:
    from tq_oracle.adapters.price_adapters.base import PriceData


class BasePriceValidator(ABC):
    """Base class for all price validators."""

    def __init__(self, config: object):
        """Initialize the validator with configuration."""
        self.config = config

    @abstractmethod
    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        """Validate prices and return result.

        Args:
            price_data: The accumulated price data from all price adapters

        Returns:
            CheckResult indicating if validation passed
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this validator."""
        pass
