import pytest

from tq_oracle.adapters.asset_adapters.idle_balances import IdleBalancesAdapter
from tq_oracle.config import OracleCLIConfig


@pytest.fixture
def config():
    return OracleCLIConfig(
        vault_address="0x277C6A642564A91ff78b008022D65683cEE5CCC5",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://eth.drpc.org",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_subvault_addresses_integration(config):
    adapter = IdleBalancesAdapter(config)

    subvaults = await adapter.fetch_subvault_addresses()

    expected_subvaults = [
        "0x90c983DC732e65DB6177638f0125914787b8Cb78",
        "0x893aa69FBAA1ee81B536f0FbE3A3453e86290080",
        "0x181cB55f872450D16aE858D532B4e35e50eaA76D",
        "0x9938A09FeA37bA681A1Bd53D33ddDE2dEBEc1dA0",
    ]

    assert len(subvaults) == len(expected_subvaults)
    assert subvaults == expected_subvaults


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_supported_assets_integration(config):
    adapter = IdleBalancesAdapter(config)

    supported_assets = await adapter.fetch_supported_assets()

    expected_assets = [
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "0xdC035D45d973E3EC169d2276DDab16f1e407384F",
    ]

    assert len(supported_assets) == len(expected_assets)
    assert supported_assets == expected_assets
