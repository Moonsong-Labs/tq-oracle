import pytest

from tq_oracle.processors.asset_aggregator import AggregatedAssets
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.processors.total_assets import calculate_total_assets


def test_calculate_total_assets_basic():
    aggregated = AggregatedAssets(
        assets={
            "0xA": 2,
            "0xB": 3,
        }
    )
    prices = PriceData(
        base_asset="0xA",
        prices={
            "0xA": 10**18,
            "0xB": 2 * 10**18,
        },
    )

    result = calculate_total_assets(aggregated, prices)

    assert result == (2 * 10**18) + (3 * 2 * 10**18)


def test_calculate_total_assets_empty_returns_zero():
    aggregated = AggregatedAssets(assets={})
    relative = PriceData(base_asset="", prices={})

    result = calculate_total_assets(aggregated, relative)

    assert result == 0


def test_calculate_total_assets_mismatched_keys_raises():
    aggregated = AggregatedAssets(
        assets={
            "0xA": 1,
            "0xB": 1,
        }
    )
    prices = PriceData(
        base_asset="0xA",
        prices={
            "0xA": 10**18,
        },
    )

    with pytest.raises(ValueError, match="different keys"):
        calculate_total_assets(aggregated, prices)
