import pytest
import json
from unittest.mock import Mock
from decimal import Decimal

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


@pytest.fixture(autouse=True)
def stub_decimals(monkeypatch):
    async def _decimals(
        self, _token_address: str
    ) -> int:  # pragma: no cover - simple stub
        return 18

    monkeypatch.setattr(CowSwapAdapter, "get_token_decimals", _decimals)


@pytest.fixture
def oseth_address(config):
    address = config.assets["OSETH"]
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


def test_oseth_is_skipped(config, oseth_address):
    adapter = CowSwapAdapter(config)
    assert oseth_address.lower() in adapter.skipped_assets


@pytest.mark.asyncio
async def test_fetch_prices_returns_previous_prices_on_unsupported_asset(
    config, eth_address
):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"
    result = await adapter.fetch_prices(
        [unsupported_address],
        PriceData(base_asset=eth_address, prices={"0x111": Decimal(1)}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices["0x111"] == 1


@pytest.mark.asyncio
async def test_fetch_prices_uses_native_quote_in_wei(
    monkeypatch, config, eth_address, usdc_address
):
    adapter = CowSwapAdapter(config)
    wbtc_address = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"

    async def _fake_native_price(token_address: str) -> Decimal:
        if token_address == usdc_address:
            return Decimal(
                "336732429.45504427"
            )  # wei per base unit from CoW API sample
        if token_address == wbtc_address:
            return Decimal(
                "303129509051.44714"
            )  # wei per base unit from CoW API sample
        raise AssertionError("unexpected token address")

    monkeypatch.setattr(adapter, "fetch_native_price", _fake_native_price)

    async def _fake_decimals(token_address: str) -> int:
        if token_address == usdc_address:
            return 6
        if token_address == wbtc_address:
            return 8
        return 18

    monkeypatch.setattr(adapter, "get_token_decimals", _fake_decimals)

    result = await adapter.fetch_prices(
        [usdc_address, wbtc_address], PriceData(base_asset=eth_address, prices={})
    )

    assert result.prices[usdc_address] == Decimal("336732429.45504427")
    assert result.prices[wbtc_address] == Decimal("303129509051.44714")
    assert result.decimals[usdc_address] == 6
    assert result.decimals[wbtc_address] == 8


@pytest.mark.asyncio
async def test_fetch_prices_returns_native_price(monkeypatch, config, eth_address):
    adapter = CowSwapAdapter(config)
    token_address = "0xToken"

    async def _fake_native_price(token_address: str) -> Decimal:
        return Decimal(
            "1.2345678901234567"
        )  # native price with fractional wei component

    monkeypatch.setattr(adapter, "fetch_native_price", _fake_native_price)

    result = await adapter.fetch_prices(
        [token_address], PriceData(base_asset=eth_address, prices={})
    )

    assert result.prices[token_address] == Decimal("1.2345678901234567")


@pytest.mark.asyncio
async def test_fetch_prices_does_not_rescale_by_token_decimals(
    monkeypatch, config, eth_address
):
    adapter = CowSwapAdapter(config)
    token_address = "0xToken"

    async def _fake_native_price(token_address: str) -> Decimal:
        return Decimal("1234.5")  # native price in wei per smallest token unit

    monkeypatch.setattr(adapter, "fetch_native_price", _fake_native_price)

    result = await adapter.fetch_prices(
        [token_address], PriceData(base_asset=eth_address, prices={})
    )

    assert result.prices[token_address] == Decimal("1234.5")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdc_integration_with_previous_prices(
    config, eth_address, usdc_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usdc_address], PriceData(base_asset=eth_address, prices={"0x111": Decimal(1)})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == Decimal(1)
    price = result.prices[usdc_address]
    assert isinstance(price, Decimal)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdt_integration_with_previous_prices(
    config, eth_address, usdt_address
):
    adapter = CowSwapAdapter(config)
    result = await adapter.fetch_prices(
        [usdt_address], PriceData(base_asset=eth_address, prices={"0x111": Decimal(1)})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == Decimal(1)
    price = result.prices[usdt_address]
    assert isinstance(price, Decimal)
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
    assert isinstance(usdc_price, Decimal)
    assert isinstance(usdt_price, Decimal)
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
        [usds_address], PriceData(base_asset=eth_address, prices={"0x111": Decimal(1)})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == Decimal(1)
    price = result.prices[usds_address]
    assert isinstance(price, Decimal)
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
    assert isinstance(usdc_price, Decimal)
    assert isinstance(usdt_price, Decimal)
    assert isinstance(usds_price, Decimal)
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


@pytest.mark.asyncio
async def test_fetch_prices_preserves_precision(monkeypatch, config, eth_address):
    adapter = CowSwapAdapter(config)
    test_asset_address = "0xTestAsset"
    high_precision_price_str = "12345.123456789123456789"

    async def fake_fetch_native_price(_):
        return Decimal(high_precision_price_str)

    monkeypatch.setattr(adapter, "fetch_native_price", fake_fetch_native_price)

    prices_accumulator = PriceData(base_asset=eth_address, prices={})
    result = await adapter.fetch_prices([test_asset_address], prices_accumulator)

    assert test_asset_address in result.prices
    assert result.prices[test_asset_address] == Decimal(high_precision_price_str)
    assert isinstance(result.prices[test_asset_address], Decimal)


@pytest.mark.asyncio
async def test_fetch_native_price_invalid_json(monkeypatch, config):
    adapter = CowSwapAdapter(config)
    test_token = "0xTestToken"

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(side_effect=json.JSONDecodeError("test", "doc", 0))

    async def fake_to_thread(*args, **kwargs):
        return mock_response

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    with pytest.raises(ValueError, match="Invalid JSON from CowSwap API"):
        await adapter.fetch_native_price(test_token)


@pytest.mark.asyncio
async def test_fetch_native_price_non_dict_response(monkeypatch, config):
    adapter = CowSwapAdapter(config)
    test_token = "0xTestToken"

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value="not a dict")

    async def fake_to_thread(*args, **kwargs):
        return mock_response

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    with pytest.raises(ValueError, match="Invalid response structure"):
        await adapter.fetch_native_price(test_token)


@pytest.mark.asyncio
async def test_fetch_native_price_missing_price_field(monkeypatch, config):
    adapter = CowSwapAdapter(config)
    test_token = "0xTestToken"

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={"other_field": "value"})

    async def fake_to_thread(*args, **kwargs):
        return mock_response

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    with pytest.raises(ValueError, match="Invalid response structure"):
        await adapter.fetch_native_price(test_token)


@pytest.mark.asyncio
async def test_fetch_native_price_invalid_price_value(monkeypatch, config):
    adapter = CowSwapAdapter(config)
    test_token = "0xTestToken"

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={"price": "not_a_number"})

    async def fake_to_thread(*args, **kwargs):
        return mock_response

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    with pytest.raises(ValueError, match="Invalid price value"):
        await adapter.fetch_native_price(test_token)


@pytest.mark.asyncio
async def test_fetch_native_price_valid_string_price(monkeypatch, config):
    adapter = CowSwapAdapter(config)
    test_token = "0xTestToken"

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={"price": "123.456"})

    async def fake_to_thread(*args, **kwargs):
        return mock_response

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    result = await adapter.fetch_native_price(test_token)
    assert result == Decimal("123.456")
    assert isinstance(result, Decimal)


@pytest.mark.asyncio
async def test_fetch_prices_skips_oseth(
    monkeypatch, config, eth_address, oseth_address
):
    adapter = CowSwapAdapter(config)

    async def fail_native_price(_):
        raise AssertionError("osETH should not be priced via CowSwap")

    async def fail_decimals(_):
        raise AssertionError("osETH decimals should not be fetched via CowSwap")

    monkeypatch.setattr(adapter, "fetch_native_price", fail_native_price)
    monkeypatch.setattr(adapter, "get_token_decimals", fail_decimals)

    prices_accumulator = PriceData(base_asset=eth_address, prices={})
    result = await adapter.fetch_prices([oseth_address], prices_accumulator)

    assert oseth_address not in result.prices
