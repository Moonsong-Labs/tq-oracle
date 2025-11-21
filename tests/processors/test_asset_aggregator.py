import pytest
from web3 import Web3

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
    protocol_assets = [[AssetData("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 1000)]]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": 1000}


@pytest.mark.asyncio
async def test_single_protocol_multiple_assets():
    """Single protocol with multiple assets."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    protocol_assets = [
        [
            AssetData(usdc, 1000),
            AssetData(usdt, 2000),
        ]
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {usdc: 1000, usdt: 2000}


@pytest.mark.asyncio
async def test_multiple_protocols_distinct_assets():
    """Multiple protocols with different assets."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    protocol_assets = [
        [AssetData(usdc, 1000)],
        [AssetData(usdt, 2000)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {usdc: 1000, usdt: 2000}


@pytest.mark.asyncio
async def test_multiple_protocols_overlapping_assets():
    """Multiple protocols with same asset should sum amounts."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    protocol_assets = [
        [AssetData(usdc, 1000)],
        [AssetData(usdc, 500)],
        [AssetData(usdc, 300)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {usdc: 1800}


@pytest.mark.asyncio
async def test_mixed_overlapping_and_distinct():
    """Mix of overlapping and distinct assets across protocols."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    eth = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    dai = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
    protocol_assets = [
        [AssetData(usdc, 1000), AssetData(eth, 5)],
        [AssetData(usdc, 500), AssetData(dai, 2000)],
        [AssetData(eth, 3)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {
        usdc: 1500,
        eth: 8,
        dai: 2000,
    }


@pytest.mark.asyncio
async def test_protocol_with_empty_assets():
    """Protocol adapter returning empty list should not affect aggregation."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    protocol_assets = [
        [AssetData(usdc, 1000)],
        [],  # empty
        [AssetData(usdc, 500)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {usdc: 1500}


@pytest.mark.asyncio
async def test_tvl_only_assets_tracked():
    """TVL-only assets should be tracked separately from totals."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    oseth = "0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38"
    extra_asset = AssetData(oseth, 250, tvl_only=True)
    protocol_assets = [
        [AssetData(usdc, 1000), extra_asset],
        [AssetData(usdc, 500)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {usdc: 1500, oseth: 250}
    assert result.tvl_only_assets == {oseth}


@pytest.mark.asyncio
async def test_address_normalization_different_cases():
    """Addresses with different cases should be aggregated as same asset."""
    usdc_checksummed = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    protocol_assets = [
        [AssetData("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 1000)],
        [AssetData("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 500)],
        [AssetData("0xA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48", 300)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {usdc_checksummed: 1800}


@pytest.mark.asyncio
async def test_address_normalization_with_tvl_only():
    """TVL-only flag should work correctly with address normalization."""
    dai_checksummed = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
    protocol_assets = [
        [AssetData("0x6B175474E89094C44Da98b954EedeAC495271d0F", 1000, tvl_only=True)],
        [AssetData("0x6b175474e89094c44da98b954eedeac495271d0f", 500, tvl_only=True)],
        [AssetData("0x6B175474E89094C44DA98B954EEDEAC495271D0F", 300, tvl_only=True)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {dai_checksummed: 1800}
    assert result.tvl_only_assets == {dai_checksummed}


@pytest.mark.asyncio
async def test_tvl_only_flag_conflict_raises_error():
    """When adapters disagree on tvl_only, a ValueError should be raised."""
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    protocol_assets = [
        [AssetData(usdc.lower(), 1000, tvl_only=False)],
        [AssetData(usdc, 500, tvl_only=True)],
    ]

    with pytest.raises(ValueError, match="conflicting tvl_only flags"):
        await compute_total_aggregated_assets(protocol_assets)


@pytest.mark.asyncio
async def test_tvl_only_flag_conflict_multiple_assets():
    """Multiple conflicting assets should all be reported."""
    dai = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
    usdt = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    protocol_assets = [
        [
            AssetData(dai, 100, tvl_only=True),
            AssetData(usdt, 200, tvl_only=True),
        ],
        [
            AssetData(dai.lower(), 50, tvl_only=False),
            AssetData(usdt.lower(), 75, tvl_only=False),
        ],
    ]

    with pytest.raises(ValueError) as exc_info:
        await compute_total_aggregated_assets(protocol_assets)

    error_msg = str(exc_info.value)
    assert "conflicting tvl_only flags" in error_msg
    assert Web3.to_checksum_address(dai) in error_msg
    assert Web3.to_checksum_address(usdt) in error_msg


@pytest.mark.asyncio
async def test_tvl_only_consistent_across_adapters_no_error():
    """When all adapters agree on tvl_only flag, no error should be raised."""
    consistent = "0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38"
    protocol_assets = [
        [AssetData(consistent, 1000, tvl_only=True)],
        [AssetData(consistent.lower(), 500, tvl_only=True)],
        [AssetData(consistent.upper(), 300, tvl_only=True)],
    ]

    result = await compute_total_aggregated_assets(protocol_assets)

    assert result.assets == {Web3.to_checksum_address(consistent): 1800}
    assert result.tvl_only_assets == {Web3.to_checksum_address(consistent)}
