import pytest

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.eth import ETHAdapter
from tq_oracle.settings import OracleSettings
from tq_oracle.settings import Network


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        hyperliquid_env="mainnet",
        cctp_env="mainnet",
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
def weth_address(config):
    address = config.assets["WETH"]
    assert address is not None
    return address


@pytest.mark.asyncio
async def test_adapter_name(config):
    adapter = ETHAdapter(config)
    assert adapter.adapter_name == "eth"


@pytest.mark.asyncio
async def test_fetch_prices_returns_empty_prices_on_unsupported_asset(
    config, eth_address
):
    adapter = ETHAdapter(config)
    unsupported_address = "0xUnsupported"

    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
async def test_fetch_prices_raises_on_unsupported_base_asset(config):
    adapter = ETHAdapter(config)
    unsupported_address = "0xUnsupported"
    with pytest.raises(ValueError, match="ETH adapter only supports ETH as base asset"):
        await adapter.fetch_prices(
            [unsupported_address], PriceData(base_asset=unsupported_address, prices={})
        )


@pytest.mark.asyncio
async def test_fetch_prices_returns_previous_prices_on_unsupported_asset(
    config, eth_address
):
    adapter = ETHAdapter(config)
    unsupported_address = "0xUnsupported"
    result = await adapter.fetch_prices(
        [unsupported_address],
        PriceData(base_asset=eth_address, prices={"0x111": 1}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices["0x111"] == 1


@pytest.mark.asyncio
async def test_fetch_prices_eth_returns_one(config, eth_address):
    adapter = ETHAdapter(config)
    result = await adapter.fetch_prices(
        [eth_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices[eth_address] == 10**18


@pytest.mark.asyncio
async def test_fetch_prices_weth_returns_one_to_one(config, eth_address, weth_address):
    adapter = ETHAdapter(config)
    result = await adapter.fetch_prices(
        [weth_address], PriceData(base_asset=eth_address, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices[weth_address] == 10**18


@pytest.mark.asyncio
async def test_fetch_prices_all_three_assets(config, eth_address, weth_address):
    adapter = ETHAdapter(config)
    result = await adapter.fetch_prices(
        [eth_address, weth_address],
        PriceData(base_asset=eth_address, prices={}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices[eth_address] == 10**18
    assert result.prices[weth_address] == 10**18


@pytest.mark.asyncio
async def test_fetch_prices_preserves_existing_prices(
    config, eth_address, weth_address
):
    adapter = ETHAdapter(config)
    result = await adapter.fetch_prices(
        [weth_address],
        PriceData(base_asset=eth_address, prices={"0x111": 123}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 123
    assert result.prices[weth_address] == 10**18


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_all_assets_integration(config, eth_address, weth_address):
    adapter = ETHAdapter(config)
    result = await adapter.fetch_prices(
        [eth_address, weth_address],
        PriceData(base_asset=eth_address, prices={"0x111": 456}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 3
    assert result.prices["0x111"] == 456
    assert result.prices[eth_address] == 10**18
    assert result.prices[weth_address] == 10**18
