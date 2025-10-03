import pytest

from tq_oracle.processors.asset_aggregator import AggregatedAssets
from tq_oracle.processors.oracle_helper import FinalPrices
from tq_oracle.report.generator import OracleReport, generate_report


@pytest.mark.asyncio
async def test_generate_report_creates_correct_structure():
    """Report should correctly map vault address, assets, and prices."""
    vault_address = "0xVault123"
    aggregated = AggregatedAssets(assets={"0xA": 1000, "0xB": 2000})
    final_prices = FinalPrices(prices={"0xA": 10**18, "0xB": 2 * 10**18})

    report = await generate_report(vault_address, aggregated, final_prices)

    assert isinstance(report, OracleReport)
    assert report.vault_address == vault_address
    assert report.total_assets == {"0xA": 1000, "0xB": 2000}
    assert report.final_prices == {"0xA": 10**18, "0xB": 2 * 10**18}


@pytest.mark.asyncio
async def test_generate_report_with_empty_data():
    """Report should handle empty assets and prices without error."""
    vault_address = "0xEmptyVault"
    aggregated = AggregatedAssets(assets={})
    final_prices = FinalPrices(prices={})

    report = await generate_report(vault_address, aggregated, final_prices)

    assert report.vault_address == vault_address
    assert report.total_assets == {}
    assert report.final_prices == {}


@pytest.mark.asyncio
async def test_report_to_dict_includes_all_fields():
    """to_dict should convert report to dictionary with all fields present."""
    vault_address = "0xVault"
    aggregated = AggregatedAssets(assets={"0xA": 500})
    final_prices = FinalPrices(prices={"0xA": 10**18})

    report = await generate_report(vault_address, aggregated, final_prices)
    report_dict = report.to_dict()

    assert isinstance(report_dict, dict)
    assert "vault_address" in report_dict
    assert "total_assets" in report_dict
    assert "final_prices" in report_dict
    assert report_dict["vault_address"] == vault_address
    assert report_dict["total_assets"] == {"0xA": 500}
    assert report_dict["final_prices"] == {"0xA": 10**18}


@pytest.mark.asyncio
async def test_report_to_dict_serializable():
    """to_dict output should be JSON-serializable for publishing."""
    import json

    vault_address = "0xSerializableVault"
    aggregated = AggregatedAssets(assets={"0xUSDC": 123456})
    final_prices = FinalPrices(prices={"0xUSDC": 987654321})

    report = await generate_report(vault_address, aggregated, final_prices)
    report_dict = report.to_dict()

    json_str = json.dumps(report_dict)
    assert isinstance(json_str, str)

    deserialized = json.loads(json_str)
    assert deserialized["vault_address"] == vault_address
    assert deserialized["total_assets"]["0xUSDC"] == 123456


@pytest.mark.asyncio
async def test_multiple_assets_and_prices_in_report():
    """Report should correctly handle multiple assets with their corresponding prices."""
    vault_address = "0xMultiAssetVault"
    aggregated = AggregatedAssets(
        assets={
            "0xUSDC": 10000,
            "0xETH": 5,
            "0xBTC": 1,
            "0xDAI": 8000,
        }
    )
    final_prices = FinalPrices(
        prices={
            "0xUSDC": 10**18,
            "0xETH": 2000 * 10**18,
            "0xBTC": 40000 * 10**18,
            "0xDAI": 10**18,
        }
    )

    report = await generate_report(vault_address, aggregated, final_prices)

    assert len(report.total_assets) == 4
    assert len(report.final_prices) == 4
    assert report.total_assets["0xETH"] == 5
    assert report.final_prices["0xBTC"] == 40000 * 10**18
