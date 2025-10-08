import pytest

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.chainlink import ChainlinkAdapter
from tq_oracle.config import OracleCLIConfig


@pytest.fixture
def config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://eth.drpc.org",
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
async def test_fetch_prices_returns_empty_prices_on_unsupported_asset(config):
    adapter = ChainlinkAdapter(config)
    unsupported_address = "0xUnsupported"

    result = await adapter.fetch_prices([unsupported_address])
    assert isinstance(result, PriceData)
    assert len(result.prices) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_prices_usdc(config):
    adapter = ChainlinkAdapter(config)
    usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    result = await adapter.fetch_prices([usdc_address])
    assert isinstance(result, PriceData)
    assert len(result.prices) == 1
    price = result.prices[usdc_address]
    assert isinstance(price, int)
    assert price >= 0
