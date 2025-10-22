from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tq_oracle.adapters.asset_adapters.base import AssetData
from tq_oracle.checks.pre_checks import PreCheckError
from tq_oracle.config import OracleCLIConfig
from tq_oracle.orchestrator import execute_oracle_flow
from tq_oracle.processors.asset_aggregator import AggregatedAssets
from tq_oracle.processors.oracle_helper import FinalPrices
from tq_oracle.report.generator import OracleReport


@pytest.fixture
def test_config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://rpc",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=True,
        private_key=None,
        safe_txn_srvc_api_key=None,
        pre_check_retries=0,
        pre_check_timeout=0.0,
    )


@pytest.mark.asyncio
async def test_all_adapters_succeed_processes_all_data(test_config):
    """All adapters succeeding should result in all asset data being processed."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch(
            "tq_oracle.orchestrator._fetch_subvault_addresses", new_callable=AsyncMock
        ) as mock_fetch_subvaults,
        patch("tq_oracle.orchestrator.get_adapter_class") as mock_get_adapter,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
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
        # Mock two subvaults
        mock_fetch_subvaults.return_value = ["0xSubvault1", "0xSubvault2"]

        # Create two mock adapters
        adapter1 = MagicMock()
        adapter1.fetch_assets = AsyncMock(return_value=[AssetData("0xA", 100)])
        adapter2 = MagicMock()
        adapter2.fetch_assets = AsyncMock(return_value=[AssetData("0xB", 200)])

        # Mock adapter class returns instances
        AdapterClass1 = MagicMock(return_value=adapter1)
        AdapterClass2 = MagicMock(return_value=adapter2)
        mock_get_adapter.side_effect = [AdapterClass1, AdapterClass2]

        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(assets={"0xA": 100, "0xB": 200})
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
        patch(
            "tq_oracle.orchestrator._fetch_subvault_addresses", new_callable=AsyncMock
        ) as mock_fetch_subvaults,
        patch("tq_oracle.orchestrator.get_adapter_class") as mock_get_adapter,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
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
        mock_fetch_subvaults.return_value = ["0xSubvault1", "0xSubvault2"]

        adapter_success = MagicMock()
        adapter_success.fetch_assets = AsyncMock(return_value=[AssetData("0xA", 100)])

        adapter_fail = MagicMock()
        adapter_fail.fetch_assets = AsyncMock(side_effect=RuntimeError("Network error"))

        AdapterClass1 = MagicMock(return_value=adapter_success)
        AdapterClass2 = MagicMock(return_value=adapter_fail)
        mock_get_adapter.side_effect = [AdapterClass1, AdapterClass2]

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
        patch(
            "tq_oracle.orchestrator._fetch_subvault_addresses", new_callable=AsyncMock
        ) as mock_fetch_subvaults,
        patch("tq_oracle.orchestrator.get_adapter_class") as mock_get_adapter,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
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
        mock_fetch_subvaults.return_value = ["0xSubvault1", "0xSubvault2"]

        adapter1 = MagicMock()
        adapter1.fetch_assets = AsyncMock(side_effect=RuntimeError("Error 1"))
        adapter2 = MagicMock()
        adapter2.fetch_assets = AsyncMock(side_effect=RuntimeError("Error 2"))

        AdapterClass1 = MagicMock(return_value=adapter1)
        AdapterClass2 = MagicMock(return_value=adapter2)
        mock_get_adapter.side_effect = [AdapterClass1, AdapterClass2]

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
async def test_pre_check_failure_stops_execution(test_config):
    """PreCheckError should stop execution before adapters are called."""
    with (
        patch(
            "tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock
        ) as mock_pre_checks,
        patch(
            "tq_oracle.orchestrator._fetch_subvault_addresses", new_callable=AsyncMock
        ) as mock_fetch_subvaults,
    ):
        mock_pre_checks.side_effect = PreCheckError("Already published")
        mock_fetch_subvaults.return_value = ["0xSubvault1"]

        with pytest.raises(PreCheckError, match="Already published"):
            await execute_oracle_flow(test_config)

        # Verify we never got to subvault fetching since pre-check failed first
        mock_fetch_subvaults.assert_not_called()


@pytest.mark.asyncio
async def test_base_asset_is_first_in_list(test_config):
    """Base asset should be first asset in aggregated list."""
    with (
        patch("tq_oracle.orchestrator.run_pre_checks", new_callable=AsyncMock),
        patch(
            "tq_oracle.orchestrator._fetch_subvault_addresses", new_callable=AsyncMock
        ) as mock_fetch_subvaults,
        patch("tq_oracle.orchestrator.get_adapter_class") as mock_get_adapter,
        patch("tq_oracle.orchestrator.PRICE_ADAPTERS") as mock_price_adapters,
        patch(
            "tq_oracle.orchestrator.compute_total_aggregated_assets",
            new_callable=AsyncMock,
        ) as mock_compute,
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
        mock_fetch_subvaults.return_value = ["0xSubvault1"]

        adapter = MagicMock()
        adapter.fetch_assets = AsyncMock(return_value=[])
        AdapterClass = MagicMock(return_value=adapter)
        mock_get_adapter.return_value = AdapterClass

        mock_price_adapters.__iter__.return_value = iter([])

        mock_compute.return_value = AggregatedAssets(
            assets={"0xFIRST": 100, "0xSECOND": 200}
        )
        mock_calc_total_assets.return_value = 100 * 10**18 + 200 * 2 * 10**18
        mock_derive.return_value = FinalPrices(prices={})
        mock_gen_report.return_value = OracleReport(
            vault_address="0xVault",
            total_assets={"0xFIRST": 100, "0xSECOND": 200},
            final_prices={},
        )

        await execute_oracle_flow(test_config)

        call_args = mock_calc_total_assets.call_args[0]
        aggregated = call_args[0]
        asset_order = list(aggregated.assets.keys())
        assert asset_order[0] == "0xFIRST"
