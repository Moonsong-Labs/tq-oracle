import pytest
import json
from unittest.mock import Mock
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.pyth import PythAdapter
from tq_oracle.settings import OracleSettings, Network


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
        pyth_enabled=True,
        pyth_staleness_threshold=60,
        pyth_max_confidence_ratio=0.03,
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


def create_mock_discovery_response(query: str):
    """Helper to create mock discovery responses based on query."""
    response = Mock()
    response.raise_for_status = Mock()

    if "eth" in query:
        response.json = Mock(
            return_value=[
                {
                    "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                    "type": "derived",
                    "attributes": {"base": "ETH", "quote_currency": "USD"},
                }
            ]
        )
    elif "usdc" in query:
        response.json = Mock(
            return_value=[
                {
                    "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                    "type": "derived",
                    "attributes": {"base": "USDC", "quote_currency": "USD"},
                }
            ]
        )
    else:
        response.json = Mock(return_value=[])

    return response


def create_mock_http_get(price_response):
    """Helper to create mock _http_get function."""

    async def mock_http_get(url, **kwargs):
        if "price_feeds" in url:
            params = kwargs.get("params", {})
            query = params.get("query", "")
            return create_mock_discovery_response(query)
        return price_response

    return mock_http_get


@pytest.mark.asyncio
async def test_fetch_prices_invalid_json(
    config, eth_address, usdc_address, monkeypatch
):
    adapter = PythAdapter(config)

    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(side_effect=json.JSONDecodeError("test", "doc", 0))

    monkeypatch.setattr(adapter, "_http_get", create_mock_http_get(mock_price_response))

    price_data = PriceData(base_asset=eth_address, prices={})

    with pytest.raises(ValueError, match="Invalid JSON from Pyth Hermes"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_non_dict_response(
    config, eth_address, usdc_address, monkeypatch
):
    adapter = PythAdapter(config)

    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value="not a dict")

    monkeypatch.setattr(adapter, "_http_get", create_mock_http_get(mock_price_response))

    price_data = PriceData(base_asset=eth_address, prices={})

    with pytest.raises(ValueError, match="Expected dict from Pyth"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_missing_parsed_field(
    config, eth_address, usdc_address, monkeypatch
):
    adapter = PythAdapter(config)

    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value={"other_field": "value"})

    monkeypatch.setattr(adapter, "_http_get", create_mock_http_get(mock_price_response))

    price_data = PriceData(base_asset=eth_address, prices={})

    with pytest.raises(ValueError, match="Missing 'parsed' field in Pyth response"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_parsed_not_list(
    config, eth_address, usdc_address, monkeypatch
):
    adapter = PythAdapter(config)

    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value={"parsed": "not a list"})

    monkeypatch.setattr(adapter, "_http_get", create_mock_http_get(mock_price_response))

    price_data = PriceData(base_asset=eth_address, prices={})

    with pytest.raises(ValueError, match="Expected list for 'parsed' field"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_invalid_feed_item(
    config, eth_address, usdc_address, monkeypatch
):
    adapter = PythAdapter(config)

    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(
        return_value={"parsed": ["not a dict", "also not a dict"]}
    )

    monkeypatch.setattr(adapter, "_http_get", create_mock_http_get(mock_price_response))

    price_data = PriceData(base_asset=eth_address, prices={})

    with pytest.raises(ValueError, match="Invalid feed item at index 0"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_discover_feed_invalid_json(config, monkeypatch):
    adapter = PythAdapter(config)

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(side_effect=json.JSONDecodeError("test", "doc", 0))

    monkeypatch.setattr(adapter, "_http_get", lambda *args, **kwargs: mock_response)

    result = await adapter._discover_feed_from_api("ETH", "USD")

    assert result is None


@pytest.mark.asyncio
async def test_discover_feed_non_list_response(config, monkeypatch):
    adapter = PythAdapter(config)

    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={"not": "a list"})

    monkeypatch.setattr(adapter, "_http_get", lambda *args, **kwargs: mock_response)

    result = await adapter._discover_feed_from_api("ETH", "USD")

    assert result is None
