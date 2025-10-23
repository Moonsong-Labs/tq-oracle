"""Report generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..report import generate_report

if TYPE_CHECKING:
    from ..processors import AggregatedAssets, FinalPrices
    from ..report import OracleReport
    from ..state import AppState


async def build_report(
    state: AppState,
    aggregated: AggregatedAssets,
    final_prices: FinalPrices,
) -> OracleReport:
    """Generate the oracle report.

    Args:
        state: Application state containing settings and logger
        aggregated: Aggregated assets
        final_prices: Final prices for assets

    Returns:
        OracleReport containing the report data
    """
    log = state.logger

    log.info("Generating report...")
    report = await generate_report(
        state.settings.vault_address_required,
        aggregated,
        final_prices,
    )

    return report
