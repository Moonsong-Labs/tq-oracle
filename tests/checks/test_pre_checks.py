from unittest.mock import patch

import pytest

from tq_oracle.checks.pre_checks import PreCheckError, run_pre_checks
from tq_oracle.config import OracleCLIConfig


@pytest.fixture
def config():
    """Minimal config for testing."""
    return OracleCLIConfig(
        vault_address="0xVAULT",
        destination="0xDEST",
        mainnet_rpc="https://eth.example",
        hl_rpc=None,
        testnet=False,
        dry_run=True,
        backoff=False,
        private_key=None,
    )


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.check_already_published")
@patch("tq_oracle.checks.pre_checks.check_pending_vote")
async def test_no_errors_when_all_checks_pass(
    mock_pending, mock_published, config
):
    """Should not raise when both checks return False."""
    mock_published.return_value = False
    mock_pending.return_value = False

    # Should not raise
    await run_pre_checks(config, "0xVAULT")

    mock_published.assert_called_once_with(config, "0xVAULT")
    mock_pending.assert_called_once_with(config, "0xVAULT")


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.check_already_published")
@patch("tq_oracle.checks.pre_checks.check_pending_vote")
async def test_raises_when_already_published(mock_pending, mock_published, config):
    """Should raise PreCheckError when already published."""
    mock_published.return_value = True

    with pytest.raises(PreCheckError, match="already published"):
        await run_pre_checks(config, "0xVAULT")

    mock_published.assert_called_once()
    mock_pending.assert_not_called()  # should short-circuit


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.check_already_published")
@patch("tq_oracle.checks.pre_checks.check_pending_vote")
async def test_raises_when_pending_vote(mock_pending, mock_published, config):
    """Should raise PreCheckError when report is pending vote."""
    mock_published.return_value = False
    mock_pending.return_value = True

    with pytest.raises(PreCheckError, match="pending vote"):
        await run_pre_checks(config, "0xVAULT")

    mock_published.assert_called_once()
    mock_pending.assert_called_once()


@pytest.mark.asyncio
@patch("tq_oracle.checks.pre_checks.check_already_published")
@patch("tq_oracle.checks.pre_checks.check_pending_vote")
async def test_includes_vault_address_in_error(
    mock_pending, mock_published, config
):
    """Error message should include vault address."""
    mock_published.return_value = True

    with pytest.raises(PreCheckError, match="0xVAULT"):
        await run_pre_checks(config, "0xVAULT")
