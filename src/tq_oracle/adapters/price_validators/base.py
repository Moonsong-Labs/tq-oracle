from __future__ import annotations

from abc import ABC, abstractmethod

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.settings import OracleSettings


class BasePriceValidator(ABC):
    """Base class for all price validators."""

    def __init__(self, config: OracleSettings):
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

    def _calculate_price_deviation_percentage(
        self, reference_price: int, actual_price: int
    ) -> float:
        """Calculate the percentage deviation between two prices.

        Args:
            reference_price: The reference price (e.g., from Chainlink)
            actual_price: The actual price being validated

        Returns:
            Absolute percentage deviation between the prices

        Raises:
            ValueError: If actual_price is zero
        """
        if actual_price == 0:
            raise ValueError("actual_price cannot be zero")

        return abs((reference_price - actual_price) / actual_price * 100)
