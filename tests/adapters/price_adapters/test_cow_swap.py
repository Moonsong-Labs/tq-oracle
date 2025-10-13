import pytest

from tq_oracle.constants import ETH_ASSET
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.cow_swap import CowSwapAdapter
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
async def test_fetch_prices_returns_empty_prices_on_unsupported_asset(config):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"

    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
async def test_fetch_prices_raises_on_unsupported_base_asset(config):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"
    with pytest.raises(
        ValueError, match="CowSwap adapter only supports ETH as base asset"
    ):
        await adapter.fetch_prices(
            [unsupported_address], PriceData(base_asset=unsupported_address, prices={})
        )


@pytest.mark.asyncio
async def test_fetch_prices_returns_previous_prices_on_unsupported_asset(config):
    adapter = CowSwapAdapter(config)
    unsupported_address = "0xUnsupported"
    result = await adapter.fetch_prices(
        [unsupported_address], PriceData(base_asset=ETH_ASSET, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    assert result.prices["0x111"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdc_integration_with_previous_prices(config):
    adapter = CowSwapAdapter(config)
    usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    result = await adapter.fetch_prices(
        [usdc_address], PriceData(base_asset=ETH_ASSET, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 1
    price = result.prices[usdc_address]
    assert isinstance(price, int)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdt_integration_with_previous_prices(config):
    adapter = CowSwapAdapter(config)
    usdt_address = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    result = await adapter.fetch_prices(
        [usdt_address], PriceData(base_asset=ETH_ASSET, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 1
    price = result.prices[usdt_address]
    assert isinstance(price, int)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdc_and_usdt_integration(config):
    adapter = CowSwapAdapter(config)
    usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt_address = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    result = await adapter.fetch_prices(
        [usdc_address, usdt_address], PriceData(base_asset=ETH_ASSET, prices={})
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
async def test_fetch_prices_usdt_not_supported_on_testnet():
    testnet_config = OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://sepolia.drpc.org",
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=True,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )
    adapter = CowSwapAdapter(testnet_config)
    usdt_address = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    result = await adapter.fetch_prices(
        [usdt_address], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usds_integration_with_previous_prices(config):
    adapter = CowSwapAdapter(config)
    usds_address = "0xdC035D45d973E3EC169d2276DDab16f1e407384F"
    result = await adapter.fetch_prices(
        [usds_address], PriceData(base_asset=ETH_ASSET, prices={"0x111": 1})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 2
    assert result.prices["0x111"] == 1
    price = result.prices[usds_address]
    assert isinstance(price, int)
    assert price >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_all_stablecoins_integration(config):
    adapter = CowSwapAdapter(config)
    usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt_address = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    usds_address = "0xdC035D45d973E3EC169d2276DDab16f1e407384F"
    result = await adapter.fetch_prices(
        [usdc_address, usdt_address, usds_address],
        PriceData(base_asset=ETH_ASSET, prices={}),
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
async def test_fetch_prices_usds_not_supported_on_testnet():
    testnet_config = OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://sepolia.drpc.org",
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=True,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )
    adapter = CowSwapAdapter(testnet_config)
    usds_address = "0xdC035D45d973E3EC169d2276DDab16f1e407384F"
    result = await adapter.fetch_prices(
        [usds_address], PriceData(base_asset=ETH_ASSET, prices={})
    )
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0
