import pytest

from tq_oracle.adapters.price_adapters.chainlink import ChainlinkAdapter
from tq_oracle.config import OracleCLIConfig


@pytest.fixture
def config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://mainnet.rpc",
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
