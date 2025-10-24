import pytest

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.cow_swap import CowSwapAdapter
from tq_oracle.settings import OracleSettings
from tq_oracle.settings import Network


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://eth.drpc.org",
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
        l1_rpc="https://sepolia.drpc.org",
        network=Network.SEPOLIA,
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        hyperliquid_env="testnet",
        cctp_env="testnet",
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
        l1_rpc="https://sepolia.drpc.org",
        network=Network.SEPOLIA,
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        hyperliquid_env="testnet",
        cctp_env="testnet",
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
