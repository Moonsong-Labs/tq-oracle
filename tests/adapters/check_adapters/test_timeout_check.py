# tests/adapters/check_adapters/test_timeout_check.py

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tq_oracle.adapters.check_adapters.timeout_check import (
    TimeoutCheckAdapter,
    format_time_remaining,
)
from tq_oracle.settings import OracleSettings


@pytest.fixture
def config():
    """Provides a default, valid OracleSettings for tests."""
    return OracleSettings(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        l1_rpc="https://eth.example",
        hl_rpc="https://hl.example",
        l1_subvault_address="0x1111111111111111111111111111111111111111",
        hl_subvault_address="0x2222222222222222222222222222222222222222",
        testnet=False,
        dry_run=True,
        private_key=None,
        safe_address=None,
        safe_txn_srvc_api_key=None,
    )


def create_mock_web3():
    """Helper to create a mock AsyncWeb3 instance."""
    mock = MagicMock()
    mock.to_checksum_address = lambda addr: addr
    mock.provider = MagicMock()
    mock.provider.disconnect = AsyncMock()
    return mock


def create_mock_oracle_contract(
    supported_assets_count=1,
    report_timestamp=1000000,
    timeout=3600,
):
    """Helper to create a mock oracle contract with configurable values."""
    mock_contract = MagicMock()

    # Mock supportedAssets() call
    mock_contract.functions.supportedAssets.return_value.call = AsyncMock(
        return_value=supported_assets_count
    )

    # Mock supportedAssetAt(0) call
    mock_contract.functions.supportedAssetAt.return_value.call = AsyncMock(
        return_value="0xASSET"
    )

    # Mock getReport(asset) call - returns DetailedReport(priceD18, timestamp, isSuspicious)
    mock_contract.functions.getReport.return_value.call = AsyncMock(
        return_value=[12345678, report_timestamp, False]
    )

    # Mock securityParams() call - returns SecurityParams with timeout at index 4
    mock_contract.functions.securityParams.return_value.call = AsyncMock(
        return_value=[0, 0, 0, 0, timeout, 0, 0]
    )

    return mock_contract


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (30, "30s"),
        (90, "1m 30s"),
        (3600, "1h 0m"),
        (3660, "1h 1m"),
        (7380, "2h 3m"),
        (86400, "24h 0m"),
    ],
)
def test_format_time_remaining(seconds, expected):
    """Test that time formatting produces human-readable output."""
    assert format_time_remaining(seconds) == expected


@pytest.mark.asyncio
async def test_timeout_elapsed_can_submit(config):
    """Test that check passes when timeout period has elapsed."""
    # Timeout = 3600, last report = 1000000, current time = 1004000
    # next_valid = 1000000 + 3600 = 1003600
    # 1004000 >= 1003600 -> CAN SUBMIT

    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        mock_oracle = create_mock_oracle_contract(
            supported_assets_count=1,
            report_timestamp=1000000,
            timeout=3600,
        )
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1004000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        assert result.passed
        assert "Timeout period elapsed" in result.message
        assert not result.retry_recommended


@pytest.mark.asyncio
async def test_timeout_not_elapsed_blocks_submission(config):
    """Test that check fails when timeout period has not elapsed."""
    # Timeout = 3600, last report = 1000000, current time = 1001000
    # next_valid = 1000000 + 3600 = 1003600
    # 1001000 < 1003600 -> CANNOT SUBMIT (2600s remaining)

    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        mock_oracle = create_mock_oracle_contract(
            supported_assets_count=1,
            report_timestamp=1000000,
            timeout=3600,
        )
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1001000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        assert not result.passed
        assert "Cannot submit" in result.message
        assert "43m 20s remaining" in result.message
        assert not result.retry_recommended


@pytest.mark.asyncio
async def test_no_previous_report_allows_submission(config):
    """Test that check passes when no previous report exists (timestamp=0)."""
    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        # Report with timestamp = 0 (no previous report)
        mock_oracle = create_mock_oracle_contract(
            supported_assets_count=1,
            report_timestamp=0,
            timeout=3600,
        )
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1001000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        assert result.passed
        assert "No previous report exists" in result.message


@pytest.mark.asyncio
async def test_ignore_flag_warns_but_passes(config):
    """Test that ignore flag allows submission with warning when timeout not elapsed."""
    config.ignore_timeout_check = True

    # Timeout = 3600, last report = 1000000, current time = 1001000
    # Normally would FAIL, but ignore flag is set

    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        mock_oracle = create_mock_oracle_contract(
            supported_assets_count=1,
            report_timestamp=1000000,
            timeout=3600,
        )
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1001000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        # Should PASS despite timeout not elapsed
        assert result.passed
        assert "WARNING" in result.message
        assert "proceeding anyway" in result.message
        assert "--ignore-timeout-check" in result.message
        assert not result.retry_recommended


@pytest.mark.asyncio
async def test_time_calculation_accuracy(config):
    """Test that time remaining calculation is accurate."""
    # Timeout = 7200 (2 hours), last report = 1000000, current time = 1004000
    # next_valid = 1000000 + 7200 = 1007200
    # remaining = 1007200 - 1004000 = 3200s = 53m 20s

    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        mock_oracle = create_mock_oracle_contract(
            supported_assets_count=1,
            report_timestamp=1000000,
            timeout=7200,
        )
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1004000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        assert not result.passed
        assert "53m 20s remaining" in result.message


@pytest.mark.asyncio
async def test_no_supported_assets_skips_check(config):
    """Test that check passes when no supported assets are configured."""
    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        # No supported assets
        mock_oracle = create_mock_oracle_contract(
            supported_assets_count=0,
            report_timestamp=1000000,
            timeout=3600,
        )
        mock_web3.eth.contract.return_value = mock_oracle
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        assert result.passed
        assert "No supported assets" in result.message


@pytest.mark.asyncio
async def test_rpc_error_handling(config):
    """Test that RPC errors are caught and reported properly."""
    with patch(
        "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
    ) as mock_web3_class:
        # Simulate RPC connection error
        mock_web3_class.side_effect = RuntimeError("RPC connection failed")

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        result = await adapter.run_check()

        assert not result.passed
        assert "Error checking oracle timeout" in result.message
        assert "RPC connection failed" in result.message
        assert not result.retry_recommended


@pytest.mark.asyncio
async def test_adapter_name(config):
    """Test that adapter has the correct name."""
    adapter = TimeoutCheckAdapter(config)
    assert adapter.name == "Oracle Timeout Check"


@pytest.mark.asyncio
async def test_provider_cleanup_on_success(config):
    """Test that Web3 provider is properly disconnected after successful check."""
    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        mock_oracle = create_mock_oracle_contract()
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1004000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        await adapter.run_check()

        mock_web3.provider.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_cleanup_on_error(config):
    """Test that Web3 provider is properly disconnected even when error occurs."""
    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = create_mock_web3()
        mock_web3_class.return_value = mock_web3

        # Simulate error during contract call
        mock_web3.eth.contract.side_effect = RuntimeError("Contract error")
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        await adapter.run_check()

        # Cleanup should still be called
        mock_web3.provider.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_cleanup_handles_no_disconnect_method(config):
    """Test that cleanup handles providers without disconnect method gracefully."""
    with (
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.AsyncWeb3"
        ) as mock_web3_class,
        patch(
            "tq_oracle.adapters.check_adapters.timeout_check.load_oracle_abi"
        ) as mock_load_abi,
    ):
        mock_web3 = MagicMock()
        mock_web3.to_checksum_address = lambda addr: addr
        # Provider without disconnect method
        mock_web3.provider = MagicMock(spec=[])

        mock_web3_class.return_value = mock_web3

        mock_oracle = create_mock_oracle_contract()
        mock_web3.eth.contract.return_value = mock_oracle
        mock_web3.eth.get_block = AsyncMock(return_value={"timestamp": 1004000})
        mock_load_abi.return_value = {}

        config._oracle_address = "0xORACLE"
        adapter = TimeoutCheckAdapter(config)
        # Should not raise an exception
        await adapter.run_check()
