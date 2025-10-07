from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tq_oracle.adapters.asset_adapters.base import AssetData
from tq_oracle.checks.pre_checks import PreCheckError
from tq_oracle.config import OracleCLIConfig
from tq_oracle.orchestrator import execute_oracle_flow
from tq_oracle.processors.asset_aggregator import AggregatedAssets
from tq_oracle.processors.oracle_helper import FinalPrices
from tq_oracle.processors.price_calculator import RelativePrices
from tq_oracle.report.generator import OracleReport


@pytest.fixture
def test_config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://rpc",
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=True,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
async def test_all_adapters_succeed_processes_all_data(test_config):
    """All adapters succeeding should result in all asset data being processed."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch("tq_oracle.orchestrator.ASSET_ADAPTERS") as mock_asset_adapters,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
        patch(
            "tq_oracle.orchestrator.calculate_relative_prices", new_callable=AsyncMock
        ) as mock_calc_prices,
        patch(
            "tq_oracle.orchestrator.calculate_total_assets"
        ) as mock_calc_total_assets,
        patch(
            "tq_oracle.orchestrator.derive_final_prices", new_callable=AsyncMock
        ) as mock_derive,
        patch(
            "tq_oracle.orchestrator.generate_report", new_callable=AsyncMock
        ) as mock_gen_report,
        patch(
            "tq_oracle.orchestrator.publish_report", new_callable=AsyncMock
        ) as mock_publish,
    ):
        adapter1 = MagicMock()
        adapter1.fetch_assets = AsyncMock(return_value=[AssetData("0xA", 100)])
        adapter2 = MagicMock()
        adapter2.fetch_assets = AsyncMock(return_value=[AssetData("0xB", 200)])

        mock_asset_adapters.__iter__.return_value = iter(
            [lambda config: adapter1, lambda config: adapter2]
        )
        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(assets={"0xA": 100, "0xB": 200})
        mock_calc_prices.return_value = RelativePrices(
            base_asset="0xA", prices={"0xA": 10**18, "0xB": 2 * 10**18}
        )
        mock_calc_total_assets.return_value = 100 * 10**18 + 200 * 2 * 10**18
        mock_derive.return_value = FinalPrices(
            prices={"0xA": 10**18, "0xB": 2 * 10**18}
        )
        mock_gen_report.return_value = OracleReport(
            vault_address="0xVault",
            total_assets={"0xA": 100, "0xB": 200},
            final_prices={"0xA": 10**18, "0xB": 2 * 10**18},
        )

        await execute_oracle_flow(test_config)

        mock_compute.assert_called_once()
        call_args = mock_compute.call_args[0][0]
        assert len(call_args) == 2
        mock_publish.assert_called_once()


@pytest.mark.asyncio
async def test_some_adapters_fail_processes_successful_ones(test_config):
    """Failed adapters should be logged but successful ones should still be processed."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch("tq_oracle.orchestrator.ASSET_ADAPTERS") as mock_asset_adapters,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
        patch(
            "tq_oracle.orchestrator.calculate_relative_prices", new_callable=AsyncMock
        ),
        patch(
            "tq_oracle.orchestrator.calculate_total_assets"
        ) as mock_calc_total_assets,
        patch(
            "tq_oracle.orchestrator.derive_final_prices", new_callable=AsyncMock
        ) as mock_derive,
        patch(
            "tq_oracle.orchestrator.generate_report", new_callable=AsyncMock
        ) as mock_gen_report,
        patch("tq_oracle.orchestrator.publish_report", new_callable=AsyncMock),
    ):
        adapter_success = MagicMock()
        adapter_success.fetch_assets = AsyncMock(return_value=[AssetData("0xA", 100)])

        adapter_fail = MagicMock()
        adapter_fail.fetch_assets = AsyncMock(side_effect=RuntimeError("Network error"))

        mock_asset_adapters.__iter__.return_value = iter(
            [lambda config: adapter_success, lambda config: adapter_fail]
        )
        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(assets={"0xA": 100})
        mock_calc_total_assets.return_value = 100 * 10**18
        mock_derive.return_value = FinalPrices(prices={"0xA": 10**18})
        mock_gen_report.return_value = OracleReport(
            vault_address="0xVault",
            total_assets={"0xA": 100},
            final_prices={"0xA": 10**18},
        )

        await execute_oracle_flow(test_config)

        call_args = mock_compute.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0][0].asset_address == "0xA"


@pytest.mark.asyncio
async def test_all_adapters_fail_handles_gracefully(test_config):
    """All adapters failing should result in empty asset data, not crash."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch("tq_oracle.orchestrator.ASSET_ADAPTERS") as mock_asset_adapters,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
        patch(
            "tq_oracle.orchestrator.calculate_relative_prices", new_callable=AsyncMock
        ),
        patch(
            "tq_oracle.orchestrator.calculate_total_assets"
        ) as mock_calc_total_assets,
        patch(
            "tq_oracle.orchestrator.derive_final_prices", new_callable=AsyncMock
        ) as mock_derive,
        patch(
            "tq_oracle.orchestrator.generate_report", new_callable=AsyncMock
        ) as mock_gen_report,
        patch("tq_oracle.orchestrator.publish_report", new_callable=AsyncMock),
    ):
        adapter1 = MagicMock()
        adapter1.fetch_assets = AsyncMock(side_effect=RuntimeError("Error 1"))
        adapter2 = MagicMock()
        adapter2.fetch_assets = AsyncMock(side_effect=RuntimeError("Error 2"))

        mock_asset_adapters.__iter__.return_value = iter(
            [lambda config: adapter1, lambda config: adapter2]
        )
        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(assets={})
        mock_calc_total_assets.return_value = 0
        mock_derive.return_value = FinalPrices(prices={})
        mock_gen_report.return_value = OracleReport(
            vault_address="0xVault", total_assets={}, final_prices={}
        )

        await execute_oracle_flow(test_config)

        call_args = mock_compute.call_args[0][0]
        assert len(call_args) == 0


@pytest.mark.asyncio
async def test_empty_assets_results_in_empty_base_asset(test_config):
    """No assets should result in empty string base asset, not crash."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch("tq_oracle.orchestrator.ASSET_ADAPTERS") as mock_asset_adapters,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
        patch(
            "tq_oracle.orchestrator.calculate_relative_prices", new_callable=AsyncMock
        ) as mock_calc_prices,
        patch(
            "tq_oracle.orchestrator.derive_final_prices", new_callable=AsyncMock
        ) as mock_derive,
        patch(
            "tq_oracle.orchestrator.generate_report", new_callable=AsyncMock
        ) as mock_gen_report,
        patch("tq_oracle.orchestrator.publish_report", new_callable=AsyncMock),
    ):
        mock_asset_adapters.__iter__.return_value = iter([])
        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(assets={})
        mock_calc_prices.return_value = RelativePrices(base_asset="", prices={})
        mock_derive.return_value = FinalPrices(prices={})
        mock_gen_report.return_value = OracleReport(
            vault_address="0xVault", total_assets={}, final_prices={}
        )

        await execute_oracle_flow(test_config)

        call_args = mock_calc_prices.call_args[0]
        asset_addresses = call_args[0]
        base_asset = call_args[2]
        assert asset_addresses == []
        assert base_asset == ""


@pytest.mark.asyncio
async def test_pre_check_failure_stops_execution(test_config):
    """PreCheckError should stop execution before adapters are called."""
    with (
        patch(
            "tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock
        ) as mock_pre_checks,
        patch("tq_oracle.orchestrator.ASSET_ADAPTERS") as mock_asset_adapters,
    ):
        mock_pre_checks.side_effect = PreCheckError("Already published")

        adapter = MagicMock()
        adapter.fetch_assets = AsyncMock()
        mock_asset_adapters.__iter__.return_value = iter([lambda config: adapter])

        with pytest.raises(PreCheckError, match="Already published"):
            await execute_oracle_flow(test_config)

        adapter.fetch_assets.assert_not_called()


@pytest.mark.asyncio
async def test_base_asset_is_first_in_list(test_config):
    """Base asset should be first asset in aggregated list."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch("tq_oracle.orchestrator.ASSET_ADAPTERS") as mock_asset_adapters,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
        patch(
            "tq_oracle.orchestrator.calculate_relative_prices", new_callable=AsyncMock
        ) as mock_calc_prices,
        patch(
            "tq_oracle.orchestrator.calculate_total_assets"
        ) as mock_calc_total_assets,
        patch(
            "tq_oracle.orchestrator.derive_final_prices", new_callable=AsyncMock
        ) as mock_derive,
        patch(
            "tq_oracle.orchestrator.generate_report", new_callable=AsyncMock
        ) as mock_gen_report,
        patch("tq_oracle.orchestrator.publish_report", new_callable=AsyncMock),
    ):
        adapter = MagicMock()
        adapter.fetch_assets = AsyncMock(return_value=[])
        mock_asset_adapters.__iter__.return_value = iter([lambda config: adapter])
        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(
            assets={"0xFIRST": 100, "0xSECOND": 200}
        )
        mock_calc_prices.return_value = RelativePrices(
            base_asset="0xFIRST", prices={"0xFIRST": 10**18, "0xSECOND": 2 * 10**18}
        )
        mock_calc_total_assets.return_value = 100 * 10**18 + 200 * 2 * 10**18
        mock_derive.return_value = FinalPrices(prices={})
        mock_gen_report.return_value = OracleReport(
            vault_address="0xVault",
            total_assets={"0xFIRST": 100, "0xSECOND": 200},
            final_prices={},
        )

        await execute_oracle_flow(test_config)

        call_args = mock_calc_prices.call_args[0]
        base_asset = call_args[2]
        asset_addresses = call_args[0]
        assert base_asset == asset_addresses[0]
