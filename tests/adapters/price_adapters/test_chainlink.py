import pytest

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
async def test_fetch_prices_raises_on_invalid_asset(config):
    adapter = ChainlinkAdapter(config)
    invalid_address = "0xInvalid"

    with pytest.raises(ValueError, match="not supported"):
        await adapter.fetch_prices([invalid_address])


@pytest.mark.asyncio
async def test_fetch_prices_usdc(config):
    adapter = ChainlinkAdapter(config)
    usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    result = await adapter.fetch_prices([usdc_address])
    assert isinstance(result, list)
    assert len(result) == 1
    pd = result[0]
    assert pd.asset_address == usdc_address
    assert isinstance(pd.price_wei, int)
    assert pd.price_wei >= 0
