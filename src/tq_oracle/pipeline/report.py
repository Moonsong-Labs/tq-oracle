"""Report generation."""

from __future__ import annotations

from ..abi import fetch_total_shares
from ..report import generate_report
from ..report import publish_report as publish_report_impl
from .context import PipelineContext


async def build_report(ctx: PipelineContext) -> None:
    """Generate the oracle report.

    Args:
        ctx: Pipeline context containing state, aggregated assets, and final prices

    Sets the report in the context.
    """
    log = ctx.state.logger
    state = ctx.state
    aggregated = ctx.aggregated_required
    final_prices = ctx.final_prices_required
    price_data = ctx.price_data_required

    # Fetch total shares from the vault's share manager
    log.info("Fetching total shares...")
    try:
        total_shares = fetch_total_shares(state.settings)
        ctx.total_shares = total_shares
        log.debug(f"Total shares: {total_shares}")
    except Exception as e:
        log.warning(f"Failed to fetch total shares: {e}")
        total_shares = 0
        ctx.total_shares = 0

    log.info("Generating report...")
    report = await generate_report(
        state.settings.vault_address_required,
        price_data.base_asset,
        ctx.total_assets_required,
        aggregated,
        final_prices,
        price_data=price_data,
        total_shares=total_shares,
    )

    ctx.report = report


async def publish_report(ctx: PipelineContext) -> None:
    """Publish the oracle report.

    Args:
        ctx: Pipeline context containing state and report

    Publishes the report to the appropriate destination based on the configuration.
    """
    s = ctx.state.settings
    report = ctx.report_required
    log = ctx.state.logger

    log.info("Publishing report (dry_run=%s)...", s.dry_run)

    await publish_report_impl(s, report)
