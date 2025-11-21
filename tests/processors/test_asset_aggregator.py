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


@pytest.mark.asyncio
async def test_tvl_only_assets_tracked():
    """TVL-only assets should be tracked separately from totals."""
    extra_asset = AssetData("0xEXTRA", 250, tvl_only=True)
    protocol_assets = [
        [AssetData("0xUSDC", 1000), extra_asset],
        [AssetData("0xUSDC", 500)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xUSDC": 1500, "0xEXTRA": 250}
    assert result.tvl_only_assets == {"0xEXTRA"}


@pytest.mark.asyncio
async def test_tvl_only_flag_conflict_raises_error():
    """When adapters disagree on tvl_only, a ValueError should be raised."""
    protocol_assets = [
        [AssetData("0xCONFLICT", 1000, tvl_only=False)],
        [AssetData("0xCONFLICT", 500, tvl_only=True)],
    ]

    with pytest.raises(ValueError, match="conflicting tvl_only flags"):
        await compute_total_aggregated_assets(protocol_assets)


@pytest.mark.asyncio
async def test_tvl_only_flag_conflict_multiple_assets():
    """Multiple conflicting assets should all be reported."""
    protocol_assets = [
        [
            AssetData("0xASSET1", 100, tvl_only=True),
            AssetData("0xASSET2", 200, tvl_only=True),
        ],
        [
            AssetData("0xASSET1", 50, tvl_only=False),
            AssetData("0xASSET2", 75, tvl_only=False),
        ],
    ]

    with pytest.raises(ValueError) as exc_info:
        await compute_total_aggregated_assets(protocol_assets)

    error_msg = str(exc_info.value)
    assert "0xASSET1" in error_msg
    assert "0xASSET2" in error_msg


@pytest.mark.asyncio
async def test_tvl_only_consistent_across_adapters_no_error():
    """When all adapters agree on tvl_only flag, no error should be raised."""
    protocol_assets = [
        [AssetData("0xCONSISTENT", 1000, tvl_only=True)],
        [AssetData("0xCONSISTENT", 500, tvl_only=True)],
        [AssetData("0xCONSISTENT", 300, tvl_only=True)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xCONSISTENT": 1800}
    assert result.tvl_only_assets == {"0xCONSISTENT"}
