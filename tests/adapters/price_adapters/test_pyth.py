import pytest
import json
from unittest.mock import Mock, AsyncMock
from decimal import Decimal
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


@pytest.mark.asyncio
async def test_fetch_prices_invalid_json(mocker, config, eth_address, usdc_address):
    adapter = PythAdapter(config)
    
    def mock_discovery_response(url, **kwargs):
        params = kwargs.get("params", {})
        query = params.get("query", "")
        
        response = Mock()
        response.raise_for_status = Mock()
        
        if "eth" in query:
            response.json = Mock(return_value=[
                {
                    "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                    "type": "derived",
                    "attributes": {"base": "ETH", "quote_currency": "USD"},
                }
            ])
        elif "usdc" in query:
            response.json = Mock(return_value=[
                {
                    "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                    "type": "derived",
                    "attributes": {"base": "USDC", "quote_currency": "USD"},
                }
            ])
        else:
            response.json = Mock(return_value=[])
        
        return response
    
    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(side_effect=json.JSONDecodeError("test", "doc", 0))
    
    async def mock_http_get(url, **kwargs):
        if "price_feeds" in url:
            return mock_discovery_response(url, **kwargs)
        return mock_price_response
    
    mocker.patch.object(adapter, "_http_get", side_effect=mock_http_get)
    
    price_data = PriceData(base_asset=eth_address, prices={})
    
    with pytest.raises(ValueError, match="Invalid JSON from Pyth Hermes"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_non_dict_response(mocker, config, eth_address, usdc_address):
    adapter = PythAdapter(config)
    
    def mock_discovery_response(url, **kwargs):
        params = kwargs.get("params", {})
        query = params.get("query", "")
        
        response = Mock()
        response.raise_for_status = Mock()
        
        if "eth" in query:
            response.json = Mock(return_value=[
                {
                    "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                    "type": "derived",
                    "attributes": {"base": "ETH", "quote_currency": "USD"},
                }
            ])
        elif "usdc" in query:
            response.json = Mock(return_value=[
                {
                    "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                    "type": "derived",
                    "attributes": {"base": "USDC", "quote_currency": "USD"},
                }
            ])
        else:
            response.json = Mock(return_value=[])
        
        return response
    
    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value="not a dict")
    
    async def mock_http_get(url, **kwargs):
        if "price_feeds" in url:
            return mock_discovery_response(url, **kwargs)
        return mock_price_response
    
    mocker.patch.object(adapter, "_http_get", side_effect=mock_http_get)
    
    price_data = PriceData(base_asset=eth_address, prices={})
    
    with pytest.raises(ValueError, match="Expected dict from Pyth"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_missing_parsed_field(mocker, config, eth_address, usdc_address):
    adapter = PythAdapter(config)
    
    def mock_discovery_response(url, **kwargs):
        params = kwargs.get("params", {})
        query = params.get("query", "")
        
        response = Mock()
        response.raise_for_status = Mock()
        
        if "eth" in query:
            response.json = Mock(return_value=[
                {
                    "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                    "type": "derived",
                    "attributes": {"base": "ETH", "quote_currency": "USD"},
                }
            ])
        elif "usdc" in query:
            response.json = Mock(return_value=[
                {
                    "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                    "type": "derived",
                    "attributes": {"base": "USDC", "quote_currency": "USD"},
                }
            ])
        else:
            response.json = Mock(return_value=[])
        
        return response
    
    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value={"other_field": "value"})
    
    async def mock_http_get(url, **kwargs):
        if "price_feeds" in url:
            return mock_discovery_response(url, **kwargs)
        return mock_price_response
    
    mocker.patch.object(adapter, "_http_get", side_effect=mock_http_get)
    
    price_data = PriceData(base_asset=eth_address, prices={})
    
    with pytest.raises(ValueError, match="Missing 'parsed' field in Pyth response"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_parsed_not_list(mocker, config, eth_address, usdc_address):
    adapter = PythAdapter(config)
    
    def mock_discovery_response(url, **kwargs):
        params = kwargs.get("params", {})
        query = params.get("query", "")
        
        response = Mock()
        response.raise_for_status = Mock()
        
        if "eth" in query:
            response.json = Mock(return_value=[
                {
                    "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                    "type": "derived",
                    "attributes": {"base": "ETH", "quote_currency": "USD"},
                }
            ])
        elif "usdc" in query:
            response.json = Mock(return_value=[
                {
                    "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                    "type": "derived",
                    "attributes": {"base": "USDC", "quote_currency": "USD"},
                }
            ])
        else:
            response.json = Mock(return_value=[])
        
        return response
    
    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value={"parsed": "not a list"})
    
    async def mock_http_get(url, **kwargs):
        if "price_feeds" in url:
            return mock_discovery_response(url, **kwargs)
        return mock_price_response
    
    mocker.patch.object(adapter, "_http_get", side_effect=mock_http_get)
    
    price_data = PriceData(base_asset=eth_address, prices={})
    
    with pytest.raises(ValueError, match="Expected list for 'parsed' field"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_fetch_prices_invalid_feed_item(mocker, config, eth_address, usdc_address):
    adapter = PythAdapter(config)
    
    def mock_discovery_response(url, **kwargs):
        params = kwargs.get("params", {})
        query = params.get("query", "")
        
        response = Mock()
        response.raise_for_status = Mock()
        
        if "eth" in query:
            response.json = Mock(return_value=[
                {
                    "id": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
                    "type": "derived",
                    "attributes": {"base": "ETH", "quote_currency": "USD"},
                }
            ])
        elif "usdc" in query:
            response.json = Mock(return_value=[
                {
                    "id": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
                    "type": "derived",
                    "attributes": {"base": "USDC", "quote_currency": "USD"},
                }
            ])
        else:
            response.json = Mock(return_value=[])
        
        return response
    
    mock_price_response = Mock()
    mock_price_response.raise_for_status = Mock()
    mock_price_response.json = Mock(return_value={"parsed": ["not a dict", "also not a dict"]})
    
    async def mock_http_get(url, **kwargs):
        if "price_feeds" in url:
            return mock_discovery_response(url, **kwargs)
        return mock_price_response
    
    mocker.patch.object(adapter, "_http_get", side_effect=mock_http_get)
    
    price_data = PriceData(base_asset=eth_address, prices={})
    
    with pytest.raises(ValueError, match="Invalid feed item at index 0"):
        await adapter.fetch_prices([usdc_address], price_data)


@pytest.mark.asyncio
async def test_discover_feed_invalid_json(mocker, config):
    adapter = PythAdapter(config)
    
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(side_effect=json.JSONDecodeError("test", "doc", 0))
    
    mocker.patch.object(adapter, "_http_get", return_value=mock_response)
    
    result = await adapter._discover_feed_from_api("ETH", "USD")
    
    assert result is None


@pytest.mark.asyncio
async def test_discover_feed_non_list_response(mocker, config):
    adapter = PythAdapter(config)
    
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={"not": "a list"})
    
    mocker.patch.object(adapter, "_http_get", return_value=mock_response)
    
    result = await adapter._discover_feed_from_api("ETH", "USD")
    
    assert result is None

