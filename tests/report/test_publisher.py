import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
from eth_typing import URI
from safe_eth.eth import EthereumClient
from safe_eth.safe.safe_tx import SafeTx
from web3 import Web3

from tq_oracle.settings import OracleSettings
from tq_oracle.report.generator import OracleReport
from tq_oracle.report.publisher import (
    build_transaction,
    publish_report,
    publish_to_stdout,
    send_to_safe,
)


@pytest.fixture
def sample_report() -> OracleReport:
    """Provides a sample OracleReport for testing."""
    return OracleReport(
        vault_address="0xVaultAddress",
        total_assets={"0xAsset1": 1000000000000000000},
        final_prices={"0xAsset1": 2000 * 10**18},
    )


@pytest.fixture
def broadcast_config() -> OracleSettings:
    """Provides a sample OracleSettings configured for broadcast mode."""
    return OracleSettings(
        vault_address="0x1234567890123456789012345678901234567890",
        oracle_helper_address="0x3234567890123456789012345678901234567890",
        vault_rpc="http://localhost:8545",
        l1_subvault_address=None,
        safe_address="0x3234567890123456789012345678901234567890",
        hl_rpc=None,
        hl_subvault_address=None,
        hyperliquid_env="mainnet",
        cctp_env="mainnet",
        dry_run=False,
        private_key="0x" + "a" * 64,
        safe_txn_srvc_api_key="0xSAFE",
    )


@pytest.fixture
def sample_safe_tx(broadcast_config: OracleSettings) -> SafeTx:
    """Provides a sample SafeTx for testing."""
    ethereum_client = EthereumClient(URI(broadcast_config.vault_rpc))
    safe_address = Web3.to_checksum_address(broadcast_config.safe_address)

    return SafeTx(
        ethereum_client=ethereum_client,
        safe_address=safe_address,
        to=Web3.to_checksum_address("0x4234567890123456789012345678901234567890"),
        value=0,
        data=b"\x12\x34\x56\x78",
        operation=0,
        safe_tx_gas=0,
        base_gas=0,
        gas_price=0,
        gas_token=Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000000"
        ),
        refund_receiver=Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000000"
        ),
        safe_nonce=42,
        safe_version="1.3.0",
        chain_id=1,
    )


@pytest.mark.asyncio
async def test_publish_to_stdout_prints_correct_json(
    capsys, sample_report: OracleReport, sample_safe_tx: SafeTx
):
    """
    Verify that publish_to_stdout correctly serializes the report
    to JSON and prints it to standard output.
    """
    expected_report = sample_report.to_dict()
    expected_safe_tx_hex = sample_safe_tx.safe_tx_hash_preimage.hex()

    await publish_to_stdout(sample_report, sample_safe_tx)

    captured = capsys.readouterr()
    assert captured.err == ""
    parsed_output = json.loads(captured.out)

    assert "report" in parsed_output
    assert parsed_output["report"] == expected_report
    assert "safe_tx_hex" in parsed_output
    assert parsed_output["safe_tx_hex"] == expected_safe_tx_hex


@pytest.mark.asyncio
@patch("tq_oracle.report.publisher.encode_submit_reports")
@patch("tq_oracle.abi.get_oracle_address_from_vault")
async def test_build_transaction_creates_valid_tx_dict(
    mock_get_oracle: MagicMock,
    mock_encode_submit_reports: MagicMock,
    broadcast_config: OracleSettings,
    sample_report: OracleReport,
):
    """
    Verify that build_transaction correctly calls the encoder and
    formats the result into the expected transaction dictionary.
    """
    expected_oracle_address = "0x2234567890123456789012345678901234567890"
    mock_get_oracle.return_value = expected_oracle_address

    mock_encode_submit_reports.return_value = (
        expected_oracle_address,
        b"\x12\x34",
    )

    tx = await build_transaction(broadcast_config, sample_report)

    mock_encode_submit_reports.assert_called_once_with(
        oracle_address=expected_oracle_address,
        report=sample_report,
    )
    assert tx == {
        "to": expected_oracle_address,
        "data": b"\x12\x34",
        "value": 0,
        "operation": 0,
    }


@pytest.mark.asyncio
@patch("tq_oracle.report.publisher.SafeTx")
@patch("tq_oracle.report.publisher.asyncio.to_thread")
@patch("tq_oracle.report.publisher.Account")
@patch("tq_oracle.report.publisher.TransactionServiceApi")
@patch("tq_oracle.report.publisher.EthereumClient")
@patch("tq_oracle.report.publisher.asyncio.sleep", new_callable=AsyncMock)
async def test_send_to_safe_happy_path(
    mock_sleep: AsyncMock,
    MockEthClient: MagicMock,
    MockTxService: MagicMock,
    MockAccount: MagicMock,
    mock_to_thread: MagicMock,
    MockSafeTx: MagicMock,
    broadcast_config: OracleSettings,
):
    """
    Verify the happy path for send_to_safe, ensuring all dependencies
    are called correctly and a valid Safe URL is returned.
    """
    transaction = {
        "to": "0x4234567890123456789012345678901234567890",
        "data": b"calldata",
        "value": 0,
        "operation": 0,
    }

    mock_account = MagicMock()
    mock_account.address = "0xSignerAddress"
    MockAccount.from_key.return_value = mock_account

    mock_get_response = MagicMock()
    mock_get_response.json.return_value = {"nonce": 42}
    mock_get_response.raise_for_status.return_value = None

    mock_tx_service_instance = MockTxService.return_value
    mock_tx_service_instance.post_transaction = MagicMock()

    async def to_thread_side_effect(func, *args, **kwargs):
        if hasattr(func, "__name__") and func.__name__ == "get":
            return mock_get_response
        return None

    mock_to_thread.side_effect = to_thread_side_effect

    mock_safe_tx_instance = MockSafeTx.return_value
    mock_safe_tx_instance.safe_tx_hash.hex.return_value = "0xTxHash"

    # Mock the chain_id property by setting the cached value
    broadcast_config._chain_id = 1

    result_url = await send_to_safe(broadcast_config, transaction)

    # We now unwrap the SecretStr before passing to Account
    assert broadcast_config.private_key is not None
    MockAccount.from_key.assert_called_once_with(
        broadcast_config.private_key.get_secret_value()
    )

    get_call = mock_to_thread.call_args_list[0]
    assert get_call.args[0].__name__ == "get"
    assert f"/api/v1/safes/{broadcast_config.safe_address}/" in get_call.args[1]

    MockSafeTx.assert_called_once()
    _, kwargs = MockSafeTx.call_args
    assert kwargs["safe_address"] == broadcast_config.safe_address
    assert kwargs["to"] == transaction["to"]
    assert kwargs["data"] == transaction["data"]
    assert kwargs["safe_nonce"] == 42
    # chain_id is derived from the RPC, so we check it's passed through
    assert "chain_id" in kwargs

    # We now unwrap the SecretStr before passing to sign
    assert broadcast_config.private_key is not None
    mock_safe_tx_instance.sign.assert_called_once_with(
        broadcast_config.private_key.get_secret_value()
    )
    mock_to_thread.assert_any_call(
        mock_tx_service_instance.post_transaction, mock_safe_tx_instance
    )

    assert "https://app.safe.global/transactions/queue" in result_url
    assert f"?safe=eth:{broadcast_config.safe_address}" in result_url
    assert "#0xTxHash" in result_url


@pytest.mark.asyncio
async def test_send_to_safe_raises_error_if_config_missing(
    broadcast_config: OracleSettings,
):
    """
    Verify that send_to_safe raises ValueError if essential config
    (safe_address, private_key) is missing.
    """
    transaction = {}
    config_no_safe = broadcast_config.model_copy(update={"safe_address": None})
    config_no_key = broadcast_config.model_copy(update={"private_key": None})

    with pytest.raises(ValueError, match="safe_address required for Broadcast mode"):
        await send_to_safe(config_no_safe, transaction)

    with pytest.raises(ValueError, match="private_key required for Broadcast mode"):
        await send_to_safe(config_no_key, transaction)


@pytest.mark.asyncio
@patch("tq_oracle.report.publisher.Account")
@patch("tq_oracle.report.publisher.asyncio.to_thread")
async def test_send_to_safe_handles_http_error_on_nonce_fetch(
    mock_to_thread: MagicMock,
    MockAccount: MagicMock,
    broadcast_config: OracleSettings,
):
    """
    Verify that an HTTP error during the nonce fetch is propagated correctly.
    """
    MockAccount.from_key.return_value = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "404 Not Found"
    )
    mock_to_thread.return_value = mock_response

    # Mock the chain_id property by setting the cached value
    broadcast_config._chain_id = 1

    with pytest.raises(requests.exceptions.HTTPError, match="404 Not Found"):
        await send_to_safe(broadcast_config, {})


@pytest.mark.asyncio
@patch("tq_oracle.report.publisher.publish_to_stdout", new_callable=AsyncMock)
@patch("tq_oracle.report.publisher.send_to_safe", new_callable=AsyncMock)
async def test_publish_report_routes_to_stdout_on_dry_run(
    mock_send_to_safe: AsyncMock,
    mock_publish_to_stdout: AsyncMock,
    broadcast_config: OracleSettings,
    sample_report: OracleReport,
):
    """
    Verify that publish_report calls publish_to_stdout when config.dry_run is True.
    """
    broadcast_config.dry_run = True

    await publish_report(broadcast_config, sample_report)

    mock_publish_to_stdout.assert_awaited_once_with(sample_report)
    mock_send_to_safe.assert_not_awaited()


@pytest.mark.asyncio
@patch("tq_oracle.report.publisher.send_to_safe", new_callable=AsyncMock)
@patch("tq_oracle.report.publisher.build_transaction", new_callable=AsyncMock)
async def test_publish_report_routes_to_broadcast_flow(
    mock_build_transaction: AsyncMock,
    mock_send_to_safe: AsyncMock,
    broadcast_config: OracleSettings,
    sample_report: OracleReport,
    caplog,
):
    """
    Verify that publish_report orchestrates the build and send flow
    when in broadcast mode.
    """
    import logging

    caplog.set_level(logging.INFO)
    broadcast_config.dry_run = False
    mock_build_transaction.return_value = {"tx": "data"}
    mock_send_to_safe.return_value = "http://safe.url"

    await publish_report(broadcast_config, sample_report)

    mock_build_transaction.assert_awaited_once_with(broadcast_config, sample_report)
    mock_send_to_safe.assert_awaited_once_with(broadcast_config, {"tx": "data"})
    assert "Transaction proposed to Safe" in caplog.text
    assert "Approve here: http://safe.url" in caplog.text


@pytest.mark.asyncio
@patch("tq_oracle.report.publisher.send_to_safe", new_callable=AsyncMock)
@patch("tq_oracle.report.publisher.build_transaction", new_callable=AsyncMock)
async def test_publish_report_handles_broadcast_error_and_exits(
    mock_build_transaction: AsyncMock,
    mock_send_to_safe: AsyncMock,
    broadcast_config: OracleSettings,
    sample_report: OracleReport,
    caplog,
):
    """
    Verify that publish_report catches ValueErrors from the broadcast flow,
    prints an error message, and exits with a non-zero status code.
    """
    import logging

    caplog.set_level(logging.ERROR)
    broadcast_config.dry_run = False
    mock_build_transaction.return_value = {"tx": "data"}
    mock_send_to_safe.side_effect = ValueError("Missing API key")

    with pytest.raises(SystemExit) as excinfo:
        await publish_report(broadcast_config, sample_report)

    assert excinfo.value.code == 1
    assert "❌ Error: Missing API key" in caplog.text


@pytest.mark.asyncio
async def test_publish_report_raises_for_unsupported_direct_mode(
    broadcast_config: OracleSettings, sample_report: OracleReport
):
    """
    Verify that publish_report raises ValueError if not in
    dry-run or broadcast mode.
    """
    broadcast_config.dry_run = False
    broadcast_config.safe_address = None

    with pytest.raises(
        ValueError,
        match="Either dry_run must be True or safe_address must be set for Broadcast mode",
    ):
        await publish_report(broadcast_config, sample_report)
