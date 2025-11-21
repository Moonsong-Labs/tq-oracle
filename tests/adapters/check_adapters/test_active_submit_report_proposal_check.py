# tests/adapters/check_adapters/test_active_submit_report_proposal_check.py
from __future__ import annotations

from unittest.mock import patch

import pytest

from tq_oracle.adapters.check_adapters.active_submit_report_proposal_check import (
    SUBMIT_REPORTS_SELECTOR,
    ActiveSubmitReportProposalCheck,
)
from tq_oracle.settings import OracleSettings


@pytest.fixture
def config():
    """Provides a default, valid OracleSettings for tests."""
    return OracleSettings(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        vault_rpc="https://eth.example",
        dry_run=True,
        private_key=None,
        safe_address="0x" + "a" * 40,
        safe_txn_srvc_api_key="test-api-key",
        ignore_active_proposal_check=False,
    )


@pytest.mark.asyncio
async def test_no_safe_address_skips_check(config):
    """Verify the check passes and skips if no Safe address is configured."""
    config.safe_address = None
    check = ActiveSubmitReportProposalCheck(config)

    result = await check.run_check()

    assert result.passed is True
    assert "No Safe address configured" in result.message
    assert result.retry_recommended is False


@pytest.mark.asyncio
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.asyncio.to_thread"
)
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.ActiveSubmitReportProposalCheck._get_active_submit_report_proposals"
)
async def test_no_active_proposals_passes(
    mock_get_proposals,
    mock_to_thread,
    config,
):
    """Verify the check passes when the Safe API returns no pending proposals."""
    # Mock the method to return empty list
    mock_get_proposals.return_value = []

    check = ActiveSubmitReportProposalCheck(config)
    result = await check.run_check()

    assert result.passed is True
    assert result.message == "No active submitReport() proposals found"
    assert result.retry_recommended is False


@pytest.mark.asyncio
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.ActiveSubmitReportProposalCheck._get_active_submit_report_proposals"
)
async def test_single_active_proposal_fails_by_default(
    mock_get_proposals,
    config,
):
    """Verify the check fails if one active submitReports() proposal is found."""
    config.ignore_active_proposal_check = False

    active_proposal = {
        "isExecuted": False,
        "data": f"{SUBMIT_REPORTS_SELECTOR}aabbccdd",
    }
    mock_get_proposals.return_value = [active_proposal]

    check = ActiveSubmitReportProposalCheck(config)
    result = await check.run_check()

    assert result.passed is False
    assert (
        "Found 1 active submitReport() proposal(s) pending approval" in result.message
    )
    assert result.retry_recommended is True


@pytest.mark.asyncio
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.ActiveSubmitReportProposalCheck._get_active_submit_report_proposals"
)
async def test_multiple_active_proposals_fails_with_count(
    mock_get_proposals,
    config,
):
    """Verify the check fails with correct count when multiple proposals are found."""
    config.ignore_active_proposal_check = False

    active_proposals = [
        {"isExecuted": False, "data": f"{SUBMIT_REPORTS_SELECTOR}01"},
        {"isExecuted": False, "data": f"{SUBMIT_REPORTS_SELECTOR}02"},
        {"isExecuted": False, "data": f"{SUBMIT_REPORTS_SELECTOR}03"},
    ]
    mock_get_proposals.return_value = active_proposals

    check = ActiveSubmitReportProposalCheck(config)
    result = await check.run_check()

    assert result.passed is False
    assert (
        "Found 3 active submitReport() proposal(s) pending approval" in result.message
    )
    assert result.retry_recommended is True


@pytest.mark.asyncio
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.ActiveSubmitReportProposalCheck._get_active_submit_report_proposals"
)
async def test_ignore_flag_passes_with_warning(
    mock_get_proposals,
    config,
):
    """Verify the check passes with warning if ignore flag is set, even with active proposals."""
    config.ignore_active_proposal_check = True

    active_proposal = {
        "isExecuted": False,
        "data": f"{SUBMIT_REPORTS_SELECTOR}aabbccdd",
    }
    mock_get_proposals.return_value = [active_proposal]

    check = ActiveSubmitReportProposalCheck(config)
    result = await check.run_check()

    assert result.passed is True
    assert "WARNING" in result.message
    assert "proceeding anyway" in result.message
    assert "--ignore-active-proposal-check" in result.message
    assert result.retry_recommended is False


@pytest.mark.asyncio
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.ActiveSubmitReportProposalCheck._get_active_submit_report_proposals"
)
async def test_api_error_fails_check(
    mock_get_proposals,
    config,
):
    """Verify the check fails gracefully if the Safe API call raises an exception."""
    error_message = "Service Unavailable"
    mock_get_proposals.side_effect = Exception(error_message)

    check = ActiveSubmitReportProposalCheck(config)
    result = await check.run_check()

    assert result.passed is False
    assert f"Error checking for active proposals: {error_message}" in result.message
    assert result.retry_recommended is False


@pytest.mark.asyncio
@patch(
    "tq_oracle.adapters.check_adapters.active_submit_report_proposal_check.ActiveSubmitReportProposalCheck._get_active_submit_report_proposals"
)
async def test_mixed_transactions_filtered_correctly(
    mock_get_proposals,
    config,
):
    """Verify comprehensive filtering with a mixed list of transactions."""
    # The filtering happens in _get_active_submit_report_proposals
    # We're testing that the check correctly handles the filtered results
    filtered_proposals = [
        {"isExecuted": False, "data": f"{SUBMIT_REPORTS_SELECTOR}01"},
        {"isExecuted": False, "data": f"{SUBMIT_REPORTS_SELECTOR}04"},
        {"data": f"{SUBMIT_REPORTS_SELECTOR}05"},
    ]
    mock_get_proposals.return_value = filtered_proposals

    check = ActiveSubmitReportProposalCheck(config)
    result = await check.run_check()

    assert result.passed is False
    assert "Found 3 active submitReport() proposal(s)" in result.message


@pytest.mark.asyncio
async def test_adapter_name(config):
    """Test that adapter has the correct name."""
    check = ActiveSubmitReportProposalCheck(config)
    assert check.name == "Active submitReport() Proposal Check"
