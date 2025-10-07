import pytest

from tq_oracle.adapters.asset_adapters.base import AssetData
from tq_oracle.processors.asset_aggregator import compute_total_aggregated_assets


@pytest.mark.asyncio
async def test_empty_protocol_assets():
    """Empty input should return empty aggregated assets."""
    result = await compute_total_aggregated_assets([])

    assert result.assets == {}


@pytest.mark.asyncio
async def test_single_protocol_single_asset():
    """Single protocol with one asset."""
    protocol_assets = [[AssetData("0xTOKEN", 1000)]]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xTOKEN": 1000}


@pytest.mark.asyncio
async def test_single_protocol_multiple_assets():
    """Single protocol with multiple assets."""
    protocol_assets = [
        [
            AssetData("0xTOKEN1", 1000),
            AssetData("0xTOKEN2", 2000),
        ]
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xTOKEN1": 1000, "0xTOKEN2": 2000}


@pytest.mark.asyncio
async def test_multiple_protocols_distinct_assets():
    """Multiple protocols with different assets."""
    protocol_assets = [
        [AssetData("0xTOKEN1", 1000)],
        [AssetData("0xTOKEN2", 2000)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xTOKEN1": 1000, "0xTOKEN2": 2000}


@pytest.mark.asyncio
async def test_multiple_protocols_overlapping_assets():
    """Multiple protocols with same asset should sum amounts."""
    protocol_assets = [
        [AssetData("0xUSDC", 1000)],
        [AssetData("0xUSDC", 500)],
        [AssetData("0xUSDC", 300)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xUSDC": 1800}


@pytest.mark.asyncio
async def test_mixed_overlapping_and_distinct():
    """Mix of overlapping and distinct assets across protocols."""
    protocol_assets = [
        [AssetData("0xUSDC", 1000), AssetData("0xETH", 5)],
        [AssetData("0xUSDC", 500), AssetData("0xDAI", 2000)],
        [AssetData("0xETH", 3)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {
        "0xUSDC": 1500,
        "0xETH": 8,
        "0xDAI": 2000,
    }


@pytest.mark.asyncio
async def test_protocol_with_empty_assets():
    """Protocol adapter returning empty list should not affect aggregation."""
    protocol_assets = [
        [AssetData("0xUSDC", 1000)],
        [],  # empty
        [AssetData("0xUSDC", 500)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xUSDC": 1500}
