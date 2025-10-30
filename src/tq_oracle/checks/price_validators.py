from __future__ import annotations

import asyncio
import logging

from ..adapters.price_adapters.base import PriceData
from ..adapters.price_validators import PRICE_VALIDATORS
from ..settings import OracleSettings

logger = logging.getLogger(__name__)


class PriceValidationError(Exception):
    """Raised when a price validation fails and execution should stop."""

    def __init__(self, message: str):
        super().__init__(message)


async def run_price_validations(
    config: OracleSettings,
    price_data: PriceData,
) -> None:
    """Run all price validators after price fetching.

    Args:
        config: CLI configuration
        price_data: The accumulated price data from all price adapters

    Raises:
        PriceValidationError: If any price validation fails

    This runs price validator checks including:
    - Chainlink price deviation validation
    - Other price validators as they are added
    """
    logger.info("Running price validations...")
    validators = [validator_cls(config) for validator_cls in PRICE_VALIDATORS]

    results = await asyncio.gather(
        *[validator.validate_prices(price_data) for validator in validators],
        return_exceptions=True,
    )

    failed_validations = []
    for validator, result in zip(validators, results):
        if isinstance(result, Exception):
            logger.error(f"Validator '{validator.name}' raised exception: {result}")
            failed_validations.append(f"{validator.name}: {str(result)}")
            continue

        from ..adapters.check_adapters.base import CheckResult

        if isinstance(result, CheckResult):
            if result.passed:
                logger.info(f"✓ {validator.name}: {result.message}")
            else:
                logger.warning(f"✗ {validator.name}: {result.message}")
                failed_validations.append(result.message)

    if failed_validations:
        error_msg = f"Price validations failed: {'; '.join(failed_validations)}"
        raise PriceValidationError(error_msg)
