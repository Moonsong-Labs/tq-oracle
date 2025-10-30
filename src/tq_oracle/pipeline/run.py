"""High-level pipeline orchestration."""

from __future__ import annotations

from ..report import publish_report
from ..state import AppState
from .assets import collect_assets
from .preflight import run_preflight
from .pricing import price_assets
from .report import build_report


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

    await run_preflight(state, vault_address)

    aggregated = await collect_assets(state)

    _price_data, _total_assets, final_prices = await price_assets(state, aggregated)

    report = await build_report(state, aggregated, final_prices)

    log.info("Publishing report (dry_run=%s)...", s.dry_run)
    await publish_report(s, report)

    log.info("Report completed", extra={"vault": vault_address})
