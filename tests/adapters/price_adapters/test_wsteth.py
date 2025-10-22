import pytest

from tq_oracle.constants import ETH_ASSET, WETH_MAINNET, WSTETH_MAINNET
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.wsteth import WstETHAdapter
from tq_oracle.config import OracleCLIConfig


@pytest.fixture
def config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://eth.drpc.org",
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
async def test_adapter_name(config):
    adapter = WstETHAdapter(config)
    assert adapter.adapter_name == "wsteth"


@pytest.mark.asyncio
async def test_fetch_prices_returns_empty_prices_on_unsupported_asset(config):
    adapter = WstETHAdapter(config)
    unsupported_address = "0xUnsupported"

    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
async def test_fetch_prices_raises_on_unsupported_base_asset(config):
    adapter = WstETHAdapter(config)
    unsupported_address = "0xUnsupported"
    with pytest.raises(
        ValueError, match="WstETH adapter only supports ETH as base asset"
    ):
        await adapter.fetch_prices(
            [unsupported_address], PriceData(base_asset=unsupported_address, prices={})
        )


@pytest.mark.asyncio
async def test_fetch_prices_returns_previous_prices_on_unsupported_asset(config):
    adapter = WstETHAdapter(config)
    unsupported_address = "0xUnsupported"
    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=ETH_ASSET, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices["0x111"] == 1


@pytest.mark.asyncio
async def test_fetch_prices_eth_returns_one(config):
    adapter = WstETHAdapter(config)
    result = await adapter.fetch_prices(
        [ETH_ASSET], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices[ETH_ASSET] == 1


@pytest.mark.asyncio
async def test_fetch_prices_weth_returns_one_to_one(config):
    adapter = WstETHAdapter(config)
    result = await adapter.fetch_prices(
        [WETH_MAINNET], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices[WETH_MAINNET] == 10**18


@pytest.mark.asyncio
async def test_fetch_prices_all_three_assets(config):
    adapter = WstETHAdapter(config)
    result = await adapter.fetch_prices(
        [ETH_ASSET, WETH_MAINNET], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices[ETH_ASSET] == 1
    assert result.prices[WETH_MAINNET] == 10**18


@pytest.mark.asyncio
async def test_fetch_prices_preserves_existing_prices(config):
    adapter = WstETHAdapter(config)
    result = await adapter.fetch_prices(
        [WETH_MAINNET], PriceData(base_asset=ETH_ASSET, prices={"0x111": 123})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 123
    assert result.prices[WETH_MAINNET] == 10**18


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_wsteth_integration(config):
    adapter = WstETHAdapter(config)
    result = await adapter.fetch_prices(
        [WSTETH_MAINNET], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    price = result.prices[WSTETH_MAINNET]
    assert isinstance(price, int)
    assert price > 10**18
    assert price < 2 * 10**18


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_all_assets_integration(config):
    adapter = WstETHAdapter(config)
    result = await adapter.fetch_prices(
        [ETH_ASSET, WETH_MAINNET, WSTETH_MAINNET],
        PriceData(base_asset=ETH_ASSET, prices={"0x111": 456}),
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 4
    assert result.prices["0x111"] == 456
    assert result.prices[ETH_ASSET] == 1
    assert result.prices[WETH_MAINNET] == 10**18
    wsteth_price = result.prices[WSTETH_MAINNET]
    assert isinstance(wsteth_price, int)

    assert wsteth_price > 10**18
    assert wsteth_price < 2 * 10**18
