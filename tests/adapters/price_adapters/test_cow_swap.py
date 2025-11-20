import pytest
from decimal import Decimal, ROUND_HALF_UP

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.cow_swap import CowSwapAdapter
from tq_oracle.settings import OracleSettings
from tq_oracle.settings import Network


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://eth.drpc.org",
        block_number=23690139,
        network=Network.MAINNET,
        safe_address=None,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.fixture
def eth_address(config):
    address = config.assets["ETH"]
    assert address is not None
    return address


@pytest.fixture
def usdc_address(config):
    address = config.assets["USDC"]
    assert address is not None
    return address


@pytest.fixture
def usdt_address(config):
    address = config.assets["USDT"]
    assert address is not None
    return address


@pytest.fixture
def usds_address(config):
    address = config.assets["USDS"]
    assert address is not None
    return address


@pytest.mark.asyncio
async def test_fetch_prices_returns_empty_prices_on_unsupported_asset(
    config, eth_address
):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"

    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
async def test_fetch_prices_raises_on_unsupported_base_asset(config, eth_address):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"
    with pytest.raises(
        ValueError, match="CowSwap adapter only supports ETH as base asset"
    ):
        await adapter.fetch_prices(
            [unsupported_address], PriceData(base_asset=unsupported_address, prices={})
        )


@pytest.mark.asyncio
async def test_fetch_prices_returns_previous_prices_on_unsupported_asset(
    config, eth_address
):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"
    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=eth_address, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices["0x111"] == 1


@pytest.mark.asyncio
async def test_fetch_prices_uses_native_quote_in_wei(monkeypatch, config, eth_address, usdc_address):
    adapter = CowSwapAdapter(config)
    wbtc_address = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"

    async def _fake_decimals(token_address: str) -> int:
        if token_address == usdc_address:
            return 6
        if token_address == wbtc_address:
            return 8
        raise AssertionError("unexpected token address")

    async def _fake_native_price(token_address: str) -> float:
        if token_address == usdc_address:
            return 336732429.45504427  # wei per base unit from CoW API sample
        if token_address == wbtc_address:
            return 303129509051.44714  # wei per base unit from CoW API sample
        raise AssertionError("unexpected token address")

    monkeypatch.setattr(adapter, "get_token_decimals", _fake_decimals)
    monkeypatch.setattr(adapter, "fetch_native_price", _fake_native_price)

    result = await adapter.fetch_prices(
        [usdc_address, wbtc_address], PriceData(base_asset=eth_address, prices={})
    )

    assert result.prices[usdc_address] == 336732429455044270000000000
    assert result.prices[wbtc_address] == 303129509051447140000000000000


@pytest.mark.asyncio
async def test_fetch_prices_scales_to_d18_with_round_half_up(monkeypatch, config, eth_address):
    adapter = CowSwapAdapter(config)
    token_address = "0xToken"

    async def _fake_decimals(token_address: str) -> int:  # pragma: no cover - deterministic
        return 6

    async def _fake_native_price(token_address: str) -> float:
        return 1.2345678901234567  # native price with fractional wei component

    monkeypatch.setattr(adapter, "get_token_decimals", _fake_decimals)
    monkeypatch.setattr(adapter, "fetch_native_price", _fake_native_price)

    result = await adapter.fetch_prices(
        [token_address], PriceData(base_asset=eth_address, prices={})
    )

    expected = int(
        Decimal("1.2345678901234567").scaleb(18).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )
    assert result.prices[token_address] == expected


@pytest.mark.asyncio
async def test_fetch_prices_does_not_rescale_by_token_decimals(monkeypatch, config, eth_address):
    adapter = CowSwapAdapter(config)
    token_address = "0xToken"

    async def _fake_decimals(token_address: str) -> int:
        return 6  # regression guard: decimals should not alter D18 price scaling

    async def _fake_native_price(token_address: str) -> float:
        return 1234.5  # native price in wei per smallest token unit

    monkeypatch.setattr(adapter, "get_token_decimals", _fake_decimals)
    monkeypatch.setattr(adapter, "fetch_native_price", _fake_native_price)

    result = await adapter.fetch_prices(
        [token_address], PriceData(base_asset=eth_address, prices={})
    )

    expected = int(
        Decimal("1234.5").scaleb(18).to_integral_value(rounding=ROUND_HALF_UP)
    )
    assert result.prices[token_address] == expected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdc_integration_with_previous_prices(
    config, eth_address, usdc_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usdc_address], PriceData(base_asset=eth_address, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 1
    price = result.prices[usdc_address]
    assert isinstance(price, int)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdt_integration_with_previous_prices(
    config, eth_address, usdt_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usdt_address], PriceData(base_asset=eth_address, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 1
    price = result.prices[usdt_address]
    assert isinstance(price, int)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdc_and_usdt_integration(
    config, eth_address, usdc_address, usdt_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usdc_address, usdt_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    usdc_price = result.prices[usdc_address]
    usdt_price = result.prices[usdt_address]
    assert isinstance(usdc_price, int)
    assert isinstance(usdt_price, int)
    assert usdc_price >= 0
    assert usdt_price >= 0


@pytest.mark.asyncio
async def test_fetch_prices_usdt_not_supported_on_testnet(eth_address, usdt_address):
    testnet_config = OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://sepolia.drpc.org",
        block_number=9522842,
        network=Network.SEPOLIA,
        safe_address=None,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )
    adapter = CowSwapAdapter(testnet_config)
    result = await adapter.fetch_prices(
        [usdt_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usds_integration_with_previous_prices(
    config, eth_address, usds_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usds_address], PriceData(base_asset=eth_address, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 1
    price = result.prices[usds_address]
    assert isinstance(price, int)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_all_stablecoins_integration(
    config, eth_address, usdc_address, usdt_address, usds_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usdc_address, usdt_address, usds_address],
        PriceData(base_asset=eth_address, prices={}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 3
    usdc_price = result.prices[usdc_address]
    usdt_price = result.prices[usdt_address]
    usds_price = result.prices[usds_address]
    assert isinstance(usdc_price, int)
    assert isinstance(usdt_price, int)
    assert isinstance(usds_price, int)
    assert usdc_price >= 0
    assert usdt_price >= 0
    assert usds_price >= 0


@pytest.mark.asyncio
async def test_fetch_prices_usds_not_supported_on_testnet(eth_address, usds_address):
    testnet_config = OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://sepolia.drpc.org",
        block_number=9522842,
        network=Network.SEPOLIA,
        safe_address=None,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )
    adapter = CowSwapAdapter(testnet_config)
    result = await adapter.fetch_prices(
        [usds_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0
