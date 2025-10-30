"""High-level pipeline orchestration."""

from __future__ import annotations

from ..state import AppState
from .assets import collect_assets
from .context import PipelineContext
from .preflight import run_preflight
from .pricing import price_assets
from .report import build_report, publish_report


async def run_report(state: AppState, vault_address: str) -> None:
    """Execute the complete oracle pipeline.

    This is a thin orchestrator that sequences the pipeline steps:
    1. Preflight checks
    2. Asset collection
    3. Pricing and validation
    4. Report generation
    5. Submission (if not dry-run)

    Args:
        state: Application state containing settings and logger
        vault_address: The vault address to report on
    """
    s = state.settings
    log = state.logger

    log.info(
        "Starting report",
        extra={
            "vault": vault_address,
            "hyperliquid_env": s.hyperliquid_env,
            "cctp_env": s.cctp_env,
            "dry_run": s.dry_run,
        },
    )

    ctx = PipelineContext(state=state, vault_address=vault_address)

    await run_preflight(ctx)
    await collect_assets(ctx)
    await price_assets(ctx)
    await build_report(ctx)
    await publish_report(ctx)

    log.info("Report completed", extra={"vault": vault_address})
