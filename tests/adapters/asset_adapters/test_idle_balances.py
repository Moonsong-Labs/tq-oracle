import pytest

from tq_oracle.adapters.asset_adapters.idle_balances import IdleBalancesAdapter
from tq_oracle.adapters.asset_adapters.base import AssetData
from tq_oracle.settings import OracleSettings
from tq_oracle.constants import ETH_ASSET, USDC_HL_MAINNET, HL_PROD_EVM_RPC


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0x277C6A642564A91ff78b008022D65683cEE5CCC5",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://eth.drpc.org",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        hyperliquid_env="mainnet",
        cctp_env="mainnet",
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_subvault_addresses_integration(config):
    adapter = IdleBalancesAdapter(config)

    subvaults = await adapter._fetch_subvault_addresses()

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

    supported_assets = await adapter._fetch_supported_assets()

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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_asset_balance_integration(config):
    adapter = IdleBalancesAdapter(config)

    subvault_address = "0x90c983DC732e65DB6177638f0125914787b8Cb78"

    usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdc_asset = await adapter._fetch_asset_balance(
        adapter.w3, subvault_address, usdc_address
    )
    assert isinstance(usdc_asset, AssetData)
    assert usdc_asset.asset_address == usdc_address
    assert isinstance(usdc_asset.amount, int)
    assert usdc_asset.amount >= 0

    weth_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    weth_asset = await adapter._fetch_asset_balance(
        adapter.w3, subvault_address, weth_address
    )
    assert isinstance(weth_asset, AssetData)
    assert weth_asset.asset_address == weth_address
    assert isinstance(weth_asset.amount, int)
    assert weth_asset.amount >= 0

    usdt_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    usdt_asset = await adapter._fetch_asset_balance(
        adapter.w3, subvault_address, usdt_address
    )
    assert isinstance(usdt_asset, AssetData)
    assert usdt_asset.asset_address == usdt_address
    assert isinstance(usdt_asset.amount, int)
    assert usdt_asset.amount >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_eth_balance_integration(config):
    adapter = IdleBalancesAdapter(config)

    subvault_address = "0x90c983DC732e65DB6177638f0125914787b8Cb78"

    eth_asset = await adapter._fetch_asset_balance(
        adapter.w3, subvault_address, ETH_ASSET
    )
    assert isinstance(eth_asset, AssetData)
    assert eth_asset.asset_address == ETH_ASSET
    assert isinstance(eth_asset.amount, int)
    assert eth_asset.amount >= 0


@pytest.fixture
def hl_config():
    return OracleSettings(
        vault_address="0x277C6A642564A91ff78b008022D65683cEE5CCC5",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://eth.drpc.org",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=HL_PROD_EVM_RPC,
        hl_subvault_address="0x90c983DC732e65DB6177638f0125914787b8Cb78",
        hyperliquid_env="mainnet",
        cctp_env="mainnet",
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_asset_balance_hyperevm_integration(hl_config):
    adapter = IdleBalancesAdapter(hl_config, chain="hyperliquid")

    hl_subvault_address = "0x90c983DC732e65DB6177638f0125914787b8Cb78"

    assert adapter.w3 is not None
    usdc_hl_asset = await adapter._fetch_asset_balance(
        adapter.w3, hl_subvault_address, USDC_HL_MAINNET
    )
    assert isinstance(usdc_hl_asset, AssetData)
    assert usdc_hl_asset.asset_address == USDC_HL_MAINNET
    assert isinstance(usdc_hl_asset.amount, int)
    assert usdc_hl_asset.amount >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_assets_integration(hl_config):
    adapter = IdleBalancesAdapter(hl_config)

    assets = await adapter.fetch_all_assets()

    expected_asset_addresses = {
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "0xdC035D45d973E3EC169d2276DDab16f1e407384F",
    }

    assert len(assets) == 24

    for asset in assets:
        assert isinstance(asset, AssetData)
        assert asset.asset_address in expected_asset_addresses
        assert isinstance(asset.amount, int)
        assert asset.amount >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_assets_without_hl_integration(config):
    adapter = IdleBalancesAdapter(config)

    assets = await adapter.fetch_all_assets()

    expected_asset_addresses = {
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "0xdC035D45d973E3EC169d2276DDab16f1e407384F",
    }

    assert len(assets) == 24

    for asset in assets:
        assert isinstance(asset, AssetData)
        assert asset.asset_address in expected_asset_addresses
        assert isinstance(asset.amount, int)
        assert asset.amount >= 0
