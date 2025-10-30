"""Report generation."""

from __future__ import annotations

from ..report import generate_report
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

    log.info("Generating report...")
    report = await generate_report(
        state.settings.vault_address_required,
        aggregated,
        final_prices,
    )

    ctx.report = report
