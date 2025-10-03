import pytest

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.processors.price_calculator import calculate_relative_prices


@pytest.mark.asyncio
async def test_base_asset_always_one():
    """Base asset should always have relative price of 10^18 (1.0)."""
    prices = [
        PriceData("0xBASE", 2000 * 10**18),  # $2000
        PriceData("0xOTHER", 1000 * 10**18),  # $1000
    ]

    result = await calculate_relative_prices(
        ["0xBASE", "0xOTHER"], prices, "0xBASE"
    )

    assert result.base_asset == "0xBASE"
    assert result.prices["0xBASE"] == 10**18


@pytest.mark.asyncio
async def test_relative_price_calculation():
    """Asset price should be relative to base asset."""
    prices = [
        PriceData("0xETH", 2000 * 10**18),  # $2000
        PriceData("0xBTC", 40000 * 10**18),  # $40000
    ]

    result = await calculate_relative_prices(
        ["0xETH", "0xBTC"], prices, "0xETH"
    )

    # BTC/ETH = 40000/2000 = 20
    assert result.prices["0xBTC"] == 20 * 10**18


@pytest.mark.asyncio
async def test_zero_base_price():
    """Zero base price should result in zero relative prices."""
    prices = [
        PriceData("0xBASE", 0),
        PriceData("0xOTHER", 1000 * 10**18),
    ]

    result = await calculate_relative_prices(
        ["0xBASE", "0xOTHER"], prices, "0xBASE"
    )

    assert result.prices["0xOTHER"] == 0


@pytest.mark.asyncio
async def test_missing_asset_in_price_map():
    """Missing asset should get zero price."""
    prices = [
        PriceData("0xBASE", 2000 * 10**18),
    ]

    result = await calculate_relative_prices(
        ["0xBASE", "0xMISSING"], prices, "0xBASE"
    )

    assert result.prices["0xMISSING"] == 0


@pytest.mark.asyncio
async def test_missing_base_asset_defaults_to_one():
    """Missing base asset should default to 1.0."""
    prices = [
        PriceData("0xOTHER", 1000 * 10**18),
    ]

    result = await calculate_relative_prices(
        ["0xBASE", "0xOTHER"], prices, "0xBASE"
    )

    # base defaults to 10^18, so 1000/1 = 1000
    assert result.prices["0xOTHER"] == 1000 * 10**18


@pytest.mark.asyncio
async def test_fractional_relative_price():
    """Asset cheaper than base should have price < 10^18."""
    prices = [
        PriceData("0xETH", 2000 * 10**18),
        PriceData("0xUSDC", 1 * 10**18),  # $1
    ]

    result = await calculate_relative_prices(
        ["0xETH", "0xUSDC"], prices, "0xETH"
    )

    # USDC/ETH = 1/2000 = 0.0005
    assert result.prices["0xUSDC"] == (10**18 // 2000)


@pytest.mark.asyncio
async def test_empty_assets_list():
    """Empty assets list should return empty prices dict."""
    prices = [PriceData("0xBASE", 1000 * 10**18)]

    result = await calculate_relative_prices([], prices, "0xBASE")

    assert result.prices == {}
