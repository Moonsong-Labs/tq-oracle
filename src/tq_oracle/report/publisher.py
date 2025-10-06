from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING

from eth_account import Account
from eth_account.signers.local import LocalAccount

from ..safe.api_client import SafeAPIClient
from ..safe.transaction_builder import encode_submit_reports

if TYPE_CHECKING:
    from ..config import OracleCLIConfig
    from .generator import OracleReport

logger = logging.getLogger(__name__)


async def publish_to_stdout(report: OracleReport) -> None:
    """Publish report to stdout (dry run mode).

    Args:
        report: The oracle report to publish

    This corresponds to the "Report published to stdout" step in the flowchart.
    """
    print(json.dumps(report.to_dict(), indent=2))


async def build_transaction(
    config: OracleCLIConfig,
    report: OracleReport,
) -> dict[str, str | bytes | int]:
    """Build a submitReports() transaction.

    Args:
        config: CLI configuration
        report: The oracle report to submit

    Returns:
        Transaction data ready to be sent

    This corresponds to the "submitReports() txn built" step in the flowchart.
    """
    to_address, calldata = encode_submit_reports(
        oracle_address=config.oracle_address,
        report=report,
    )

    return {
        "to": to_address,
        "data": calldata,
        "value": 0,
        "operation": 0,  # CALL
    }


async def send_to_safe(
    config: OracleCLIConfig,
    transaction: dict[str, str | bytes | int],
) -> str:
    """Send transaction to Gnosis Safe for signing.

    Args:
        config: CLI configuration with Safe details
        transaction: The transaction to send

    Returns:
        Safe UI URL for transaction approval

    This corresponds to the "send txn to Safe" and "txn appears on Safe for signing" steps.

    Raises:
        ValueError: If safe_address or private_key is not configured
    """
    if not config.safe_address:
        raise ValueError("safe_address required for Broadcast mode")

    if not config.private_key:
        raise ValueError("private_key required for Broadcast mode")

    account: LocalAccount = Account.from_key(config.private_key)  # type: ignore[arg-type]
    logger.info("Proposing transaction as: %s", account.address)

    client = SafeAPIClient(
        chain_id=config.chain_id,
        safe_address=config.safe_address,
        rpc_url=config.mainnet_rpc,
    )

    safe_info = client.get_safe_info()
    owners = safe_info["owners"]
    threshold = safe_info["threshold"]

    num_owners = len(owners) if isinstance(owners, list) else 0

    logger.info(
        "Safe: %s, Threshold: %d/%d",
        config.safe_address,
        threshold if isinstance(threshold, int) else 0,
        num_owners,
    )

    to_addr = transaction["to"]
    data = transaction["data"]
    value = transaction.get("value", 0)
    operation = transaction.get("operation", 0)

    assert isinstance(to_addr, str), "to must be string"
    assert isinstance(data, bytes), "data must be bytes"
    assert isinstance(value, int), "value must be int"
    assert isinstance(operation, int), "operation must be int"

    safe_tx_hash = client.propose_transaction(
        to=to_addr,
        data=data,
        value=value,
        operation=operation,
        sender=account.address,
        origin="tq-oracle",
    )

    logger.info("Transaction proposed: %s", safe_tx_hash)

    safe_tx_hash_bytes = bytes.fromhex(safe_tx_hash.removeprefix("0x"))
    signature = account.unsafe_sign_hash(safe_tx_hash_bytes)  # type: ignore[arg-type]
    signature_hex = signature.signature.hex()
    client.confirm_transaction(safe_tx_hash, signature_hex)

    ui_url = client.get_safe_ui_url(safe_tx_hash)
    return ui_url


async def publish_report(
    config: OracleCLIConfig,
    report: OracleReport,
) -> None:
    """Publish the oracle report based on configuration.

    Args:
        config: CLI configuration (determines dry run vs real submission)
        report: The oracle report to publish

    This handles the branching logic in the flowchart:
    - If dry_run: publish to stdout
    - If not dry_run and Broadcast mode: build transaction, send to Safe
    - If not dry_run and direct mode: raise NotImplementedError (future work)
    """
    if config.dry_run:
        await publish_to_stdout(report)
    elif config.is_broadcast:
        try:
            transaction = await build_transaction(config, report)
            safe_url = await send_to_safe(config, transaction)
            print("\nTransaction proposed to Safe")
            print(f"Approve here: {safe_url}")
        except ValueError as e:
            print(f"\n❌ Error: {e}", file=sys.stderr)
            raise SystemExit(1) from e
    else:
        raise NotImplementedError(
            "Direct transaction submission not yet implemented. "
            "Use --safe-address for Broadcast mode or --dry-run for testing."
        )
