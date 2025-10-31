from __future__ import annotations

from dataclasses import dataclass

from ..state import AppState
from ..processors import AggregatedAssets
from ..processors import FinalPrices
from ..adapters.price_adapters.base import PriceData
from ..report import OracleReport


@dataclass
class PipelineContext:
    state: AppState
    vault_address: str
    aggregated: AggregatedAssets | None = None
    price_data: PriceData | None = None
    total_assets: int | None = None
    final_prices: FinalPrices | None = None
    report: OracleReport | None = None

    @property
    def aggregated_required(self) -> AggregatedAssets:
        if self.aggregated is None:
            raise RuntimeError(
                "Aggregated assets have not been set. Ensure collect_assets() is called before accessing this property."
            )
        return self.aggregated

    @property
    def price_data_required(self) -> PriceData:
        if self.price_data is None:
            raise RuntimeError(
                "Price data has not been set. Ensure price_assets() is called before accessing this property."
            )
        return self.price_data

    @property
    def total_assets_required(self) -> int:
        if self.total_assets is None:
            raise RuntimeError(
                "Total assets have not been set. Ensure price_assets() is called before accessing this property."
            )
        return self.total_assets

    @property
    def final_prices_required(self) -> FinalPrices:
        if self.final_prices is None:
            raise RuntimeError(
                "Final prices have not been set. Ensure price_assets() is called before accessing this property."
            )
        return self.final_prices

    @property
    def report_required(self) -> OracleReport:
        if self.report is None:
            raise RuntimeError(
                "Report has not been set. Ensure build_report() is called before accessing this property."
            )
        return self.report
