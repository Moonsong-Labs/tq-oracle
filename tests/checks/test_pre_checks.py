from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.checks.pre_checks import PreCheckError, run_pre_checks
from tq_oracle.settings import OracleSettings


@pytest.fixture
def config():
    """Minimal config for testing."""
    return OracleSettings(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        vault_rpc="https://eth.example",
        safe_address=None,
        dry_run=True,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.CHECK_ADAPTERS")
async def test_no_errors_when_all_checks_pass(mock_adapters, config):
    """Should not raise when all adapters return passing results."""
    mock_adapter1 = MagicMock()
    mock_adapter1.name = "Test Check 1"
    mock_adapter1.run_check = AsyncMock(
        return_value=CheckResult(passed=True, message="Check 1 passed")
    )

    mock_adapter2 = MagicMock()
    mock_adapter2.name = "Test Check 2"
    mock_adapter2.run_check = AsyncMock(
        return_value=CheckResult(passed=True, message="Check 2 passed")
    )

    mock_adapters.__iter__.return_value = [
        lambda config: mock_adapter1,
        lambda config: mock_adapter2,
    ]

    # Should not raise
    await run_pre_checks(config)


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.CHECK_ADAPTERS")
async def test_raises_when_check_fails(mock_adapters, config):
    """Should raise PreCheckError when any adapter returns failing result."""
    mock_adapter = MagicMock()
    mock_adapter.name = "Failing Check"
    mock_adapter.run_check = AsyncMock(
        return_value=CheckResult(
            passed=False,
            message="Check failed: issue detected",
            retry_recommended=False,
        )
    )

    mock_adapters.__iter__.return_value = [lambda config: mock_adapter]

    with pytest.raises(PreCheckError, match="Pre-checks failed"):
        await run_pre_checks(config)


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.CHECK_ADAPTERS")
async def test_includes_failure_message_in_error(mock_adapters, config):
    """Error message should include the check failure message."""
    mock_adapter = MagicMock()
    mock_adapter.name = "Test Check"
    mock_adapter.run_check = AsyncMock(
        return_value=CheckResult(
            passed=False,
            message="Report already published for vault 0xVAULT",
            retry_recommended=False,
        )
    )

    mock_adapters.__iter__.return_value = [lambda config: mock_adapter]

    with pytest.raises(PreCheckError, match="already published"):
        await run_pre_checks(config)


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.CHECK_ADAPTERS")
async def test_handles_adapter_exception(mock_adapters, config):
    """Should raise PreCheckError when adapter raises exception."""
    mock_adapter = MagicMock()
    mock_adapter.name = "Exception Check"
    mock_adapter.run_check = AsyncMock(side_effect=RuntimeError("Adapter error"))

    mock_adapters.__iter__.return_value = [lambda config: mock_adapter]

    with pytest.raises(PreCheckError, match="Pre-checks failed"):
        await run_pre_checks(config)
