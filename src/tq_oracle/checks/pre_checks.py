from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..adapters.check_adapters import CHECK_ADAPTERS
from ..adapters.check_adapters.base import CheckResult

if TYPE_CHECKING:
    from ..settings import OracleSettings

logger = logging.getLogger(__name__)


class PreCheckError(Exception):
    """Raised when a pre-check fails and execution should stop."""

    def __init__(self, message: str, retry_recommended: bool = False):
        super().__init__(message)
        self.retry_recommended = retry_recommended


async def run_pre_checks(
    config: OracleSettings,
    vault_address: str,
) -> None:
    """Run all pre-checks before proceeding with oracle flow.

    Args:
        config: CLI configuration
        vault_address: The vault contract address

    Raises:
        PreCheckError: If any pre-check fails

    This runs adapter-based checks including:
    - Safe state validation (already published, pending vote)
    - CCTP bridge in-flight detection
    - Other adapter checks
    """
    logger.info("Running pre-checks...")
    adapters = [adapter_cls(config) for adapter_cls in CHECK_ADAPTERS]

    results = await asyncio.gather(
        *[adapter.run_check() for adapter in adapters],
        return_exceptions=True,
    )

    failed_checks = []
    retry_recommended = False
    for adapter, result in zip(adapters, results):
        if isinstance(result, Exception):
            logger.error(f"Check '{adapter.name}' raised exception: {result}")
            failed_checks.append(f"{adapter.name}: {str(result)}")
            continue

        if isinstance(result, CheckResult):
            if result.passed:
                logger.info(f"✓ {adapter.name}: {result.message}")
            else:
                logger.warning(f"✗ {adapter.name}: {result.message}")
                failed_checks.append(result.message)
                # Retry if ANY failed check recommends it
                if result.retry_recommended:
                    retry_recommended = True

    if failed_checks:
        error_msg = f"Pre-checks failed: {'; '.join(failed_checks)}"
        raise PreCheckError(error_msg, retry_recommended=retry_recommended)
