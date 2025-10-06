from unittest.mock import MagicMock, patch

import pytest

from tq_oracle.adapters.asset_adapters.hyperliquid import HyperliquidAdapter
from tq_oracle.config import OracleCLIConfig
from tq_oracle.constants import (
    HL_MAINNET_API_URL,
    HL_TESTNET_API_URL,
    USDC_MAINNET,
    USDC_SEPOLIA,
)


@pytest.fixture
def mainnet_config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_address="0xOracle",
        mainnet_rpc="https://mainnet.rpc",
        safe_address=None,
        chain_id=1,
        hl_rpc=None,
        testnet=False,
        dry_run=False,
        backoff=False,
        private_key=None,
    )


@pytest.fixture
def testnet_config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_address="0xOracle",
        mainnet_rpc="https://testnet.rpc",
        safe_address=None,
        chain_id=11155111,
        hl_rpc=None,
        testnet=True,
        dry_run=False,
        backoff=False,
        private_key=None,
    )


@pytest.mark.asyncio
async def test_mainnet_uses_correct_api_and_usdc(mainnet_config):
    """Mainnet config should use mainnet API URL and USDC address."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[1, "100.0"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        mock_info_class.assert_called_once_with(
            base_url=HL_MAINNET_API_URL, skip_ws=False
        )
        assert len(assets) == 1
        assert assets[0].asset_address == USDC_MAINNET


@pytest.mark.asyncio
async def test_testnet_uses_correct_api_and_usdc(testnet_config):
    """Testnet config should use testnet API URL and USDC address."""
    adapter = HyperliquidAdapter(testnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[1, "50.0"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        mock_info_class.assert_called_once_with(
            base_url=HL_TESTNET_API_URL, skip_ws=False
        )
        assert len(assets) == 1
        assert assets[0].asset_address == USDC_SEPOLIA


@pytest.mark.asyncio
async def test_twap_calculation_with_multiple_values(mainnet_config):
    """TWAP should be correctly calculated as average of multiple values."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[
                (
                    "day",
                    {
                        "accountValueHistory": [
                            [1, "100.0"],
                            [2, "200.0"],
                            [3, "300.0"],
                        ]
                    },
                )
            ]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        expected_twap = (100.0 + 200.0 + 300.0) / 3
        expected_amount = int(expected_twap * 1e18)
        assert assets[0].amount == expected_amount


@pytest.mark.asyncio
async def test_single_value_twap_equals_that_value(mainnet_config):
    """Single value in history should result in TWAP equal to that value."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[1, "42.5"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        expected_amount = int(42.5 * 1e18)
        assert assets[0].amount == expected_amount


@pytest.mark.asyncio
async def test_empty_account_history_returns_empty(mainnet_config):
    """Empty account history should return empty asset list, not error."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": []})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        assert assets == []


@pytest.mark.asyncio
async def test_mixed_valid_invalid_values_skips_invalid(mainnet_config):
    """Invalid values in history should be skipped, TWAP calculated from valid ones only."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[
                (
                    "day",
                    {
                        "accountValueHistory": [
                            [1, "100.0"],
                            [2, "not_a_number"],
                            [3, "200.0"],
                            [4, None],
                            [5, "300.0"],
                        ]
                    },
                )
            ]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        expected_twap = (100.0 + 200.0 + 300.0) / 3
        expected_amount = int(expected_twap * 1e18)
        assert assets[0].amount == expected_amount


@pytest.mark.asyncio
async def test_all_invalid_values_returns_empty(mainnet_config):
    """All invalid values should result in empty asset list, not crash."""
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

        assets = await adapter.fetch_assets("0xSubvault")

        assert assets == []


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
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[1, "100.0"]]})]
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
    """Float TWAP should be converted to int with 1e18 precision."""
    adapter = HyperliquidAdapter(mainnet_config)

    with patch("tq_oracle.adapters.asset_adapters.hyperliquid.Info") as mock_info_class:
        mock_info = MagicMock()
        mock_info.portfolio = MagicMock(
            return_value=[("day", {"accountValueHistory": [[1, "123.456789"]]})]
        )
        mock_info_class.return_value = mock_info

        assets = await adapter.fetch_assets("0xSubvault")

        assert isinstance(assets[0].amount, int)
        assert assets[0].amount == int(123.456789 * 1e18)
