from unittest.mock import MagicMock, patch

import pytest
import time

from tq_oracle.adapters.asset_adapters.hyperliquid import HyperliquidAdapter
from tq_oracle.config import OracleCLIConfig
from tq_oracle.constants import (
    HL_MAINNET_API_URL,
    HL_TESTNET_API_URL,
    HL_MAX_PORTFOLIO_STALENESS_SECONDS,
)
from tq_oracle.config import Network


@pytest.fixture
def mainnet_config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://mainnet.rpc",
        network=Network.MAINNET,
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.fixture
def testnet_config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://testnet.rpc",
        network=Network.SEPOLIA,
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=True,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.fixture
def usdc_address(config):
    address = config.assets["USDC"]
    assert address is not None
    return address


@pytest.mark.asyncio
async def test_mainnet_uses_correct_api_and_usdc(mainnet_config):
    """Mainnet config should use mainnet API URL and USDC address."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        mock_info_class.assert_called_once_with(
            base_url=HL_MAINNET_API_URL, skip_ws=True
        )
        assert len(assets) == 1
        assert assets[0].asset_address == usdc_address(mainnet_config)


@pytest.mark.asyncio
async def test_testnet_uses_correct_api_and_usdc(testnet_config):
    """Testnet config should use testnet API URL and USDC address."""
    adapter = HyperliquidAdapter(testnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "50.0"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        mock_info_class.assert_called_once_with(
            base_url=HL_TESTNET_API_URL, skip_ws=True
        )
        assert len(assets) == 1
        assert assets[0].asset_address == usdc_address(testnet_config)


@pytest.mark.asyncio
async def test_uses_latest_value_with_multiple_history_points(mainnet_config):
    """Adapter uses the latest value from history."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[
                (
                    "day",
                    {
                        "accountValueHistory": [
                            [now_ms - 10_000, "100.0"],
                            [now_ms - 5_000, "200.0"],
                            [now_ms, "300.0"],
                        ]
                    },
                )
            ]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        expected_amount = int(300.0 * 1e18)
        assert assets[0].amount == expected_amount


@pytest.mark.asyncio
async def test_single_value_returns_that_value(mainnet_config):
    """Single value in history returns that value."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "42.5"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        expected_amount = int(42.5 * 1e18)
        assert assets[0].amount == expected_amount


@pytest.mark.asyncio
async def test_empty_account_history_raises_error(mainnet_config):
    """Empty account history should raise a ValueError."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": []})]
        )
        mock_info_class.return_value = mock_info

        with pytest.raises(ValueError, match="empty account history"):
            await adapter.fetch_assets("0xSubvault")


@pytest.mark.asyncio
async def test_mixed_valid_invalid_values_skips_invalid(mainnet_config):
    """Invalid values in history should be skipped; latest valid value is used."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[
                (
                    "day",
                    {
                        "accountValueHistory": [
                            [now_ms - 30_000, "100.0"],
                            [now_ms - 20_000, "not_a_number"],
                            [now_ms - 10_000, "200.0"],
                            [now_ms - 5_000, None],
                            [now_ms, "300.0"],
                        ]
                    },
                )
            ]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        expected_amount = int(300.0 * 1e18)
        assert assets[0].amount == expected_amount


@pytest.mark.asyncio
async def test_all_invalid_values_raises_error(mainnet_config):
    """All invalid values should raise ValueError (no valid latest value)."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[
                (
                    "day",
                    {
                        "accountValueHistory": [
                            [1, "invalid"],
                            [2, None],
                            [3, "also_bad"],
                        ]
                    },
                )
            ]
        )
        mock_info_class.return_value = mock_info

        with pytest.raises(ValueError, match="no valid latest value"):
            await adapter.fetch_assets("0xSubvault")


@pytest.mark.asyncio
async def test_missing_day_period_raises_error(mainnet_config):
    """Missing 'day' period in portfolio data should raise ValueError."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("week", {"accountValueHistory": [[1, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        with pytest.raises(ValueError, match="No 'day' period data"):
            await adapter.fetch_assets("0xSubvault")


@pytest.mark.asyncio
async def test_fetch_succeeds_with_valid_data(mainnet_config):
    """Fetch should succeed with valid day period data."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        result = await adapter.fetch_assets("0xSubvault")

        assert len(result) == 1
        assert result[0].amount == int(100.0 * 1e18)


@pytest.mark.asyncio
async def test_exception_propagates_on_api_failure(mainnet_config):
    """API failures should propagate as exceptions."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(side_effect=RuntimeError("API failure"))
        mock_info_class.return_value = mock_info

        with pytest.raises(RuntimeError, match="API failure"):
            await adapter.fetch_assets("0xSubvault")


@pytest.mark.asyncio
async def test_amount_precision_conversion(mainnet_config):
    """Float latest value should be converted to int with 1e18 precision."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "123.456789"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        assert isinstance(assets[0].amount, int)
        assert assets[0].amount == int(123.456789 * 1e18)


@pytest.mark.asyncio
async def test_hl_subvault_address_from_config_overrides_parameter(mainnet_config):
    """Config's hl_subvault_address should override the fetch_assets parameter."""
    config_with_subvault = OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://mainnet.rpc",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address="0xConfigSubvault",
        testnet=False,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )
    adapter = HyperliquidAdapter(config_with_subvault)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        await adapter.fetch_assets("0xPassedSubvault")

        # Verify portfolio was called with config's subvault, not the passed parameter
        mock_info.portfolio.assert_called_once_with(user="0xConfigSubvault")


@pytest.mark.asyncio
async def test_fallback_to_parameter_when_no_hl_subvault_in_config(mainnet_config):
    """When config has no hl_subvault_address, should use fetch_assets parameter."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[now_ms, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        await adapter.fetch_assets("0xPassedSubvault")

        # Verify portfolio was called with the passed parameter
        mock_info.portfolio.assert_called_once_with(user="0xPassedSubvault")


@pytest.mark.asyncio
async def test_accepts_timestamp_exactly_at_staleness_threshold(mainnet_config):
    """Should accept portfolio value exactly at the staleness threshold."""
    adapter = HyperliquidAdapter(mainnet_config)

    with (
        patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class,
        patch("tq_oracle.adapters.asset_adapters.hyperliquid.time.time") as mock_time,
    ):
        mock_info = MagicMock()
        now_ms = 1000000000000  # Fixed timestamp
        mock_time.return_value = now_ms / 1000
        boundary_ts = now_ms - (HL_MAX_PORTFOLIO_STALENESS_SECONDS * 1000)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[boundary_ts, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")
        assert len(assets) == 1
        assert assets[0].amount == int(100.0 * 1e18)


@pytest.mark.asyncio
async def test_raises_on_stale_portfolio_value(mainnet_config):
    """Should raise ValueError if portfolio value exceeds staleness threshold."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        now_ms = int(time.time() * 1000)
        stale_ts = now_ms - (HL_MAX_PORTFOLIO_STALENESS_SECONDS * 1000 + 1)
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[stale_ts, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        with pytest.raises(ValueError, match="stale portfolio value"):
            await adapter.fetch_assets("0xSubvault")
