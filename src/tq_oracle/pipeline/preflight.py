"""Preflight checks before executing the oracle flow."""

from __future__ import annotations

from typing import Any

import backoff

from ..checks.pre_checks import PreCheckError, run_pre_checks
from .context import PipelineContext


async def run_preflight(ctx: PipelineContext) -> None:
    """Run pre-flight checks with retry logic.

    Args:
        ctx: Pipeline context containing state and vault address

    Raises:
        PreCheckError: If pre-checks fail after all retries
    """
    s = ctx.state.settings
    log = ctx.state.logger

    log.info(
        "Running pre-checks (max retries: %d, timeout: %.1fs)...",
        s.pre_check_retries,
        s.pre_check_timeout,
    )

    def _should_giveup(e: Exception) -> bool:
        """Determine if we should give up retrying based on the exception."""
        return isinstance(e, PreCheckError) and not e.retry_recommended

    def _on_backoff(details: Any) -> None:
        """Log retry attempts."""
        log.warning(
            "Pre-check failed (attempt %d of %d): %s",
            details["tries"],
            s.pre_check_retries + 1,
            details.get("exception", details.get("value")),
        )

    def _on_giveup(details: Any) -> None:
        """Log when we give up retrying."""
        exc = details.get("exception", details.get("value"))
        if isinstance(exc, PreCheckError) and not exc.retry_recommended:
            log.error("Pre-check failed (retry not recommended): %s", exc)
        else:
            log.error(
                "Pre-checks failed after %d attempts: %s",
                details["tries"],
                exc,
            )

    @backoff.on_exception(
        backoff.constant,
        PreCheckError,
        max_tries=s.pre_check_retries + 1,
        interval=s.pre_check_timeout,
        giveup=_should_giveup,
        on_backoff=_on_backoff,
        on_giveup=_on_giveup,
    )
    async def _run_pre_checks_with_retry() -> None:
        """Run pre-checks with automatic retry on retriable errors."""
        await run_pre_checks(s)

    await _run_pre_checks_with_retry()
    log.info("Pre-checks passed successfully")
