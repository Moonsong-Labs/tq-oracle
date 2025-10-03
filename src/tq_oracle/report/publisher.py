from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import OracleCLIConfig
    from .generator import OracleReport


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
) -> dict[str, object]:
    """Build a submitReport() transaction.

    Args:
        config: CLI configuration
        report: The oracle report to submit

    Returns:
        Transaction data ready to be sent

    This corresponds to the "submitReport() txn built" step in the flowchart.

    TODO: Implement actual transaction building with Web3
    """
    return {
        "to": config.destination,
        "data": "0x",  # Placeholder
        "value": 0,
    }


async def send_to_safe(
    config: OracleCLIConfig,
    transaction: dict[str, object],
) -> str:
    """Send transaction to Gnosis Safe for signing.

    Args:
        config: CLI configuration with Safe details
        transaction: The transaction to send

    Returns:
        Transaction hash or Safe URL

    This corresponds to the "send txn to Safe" and "txn appears on Safe for signing" steps.

    TODO: Implement actual Safe API integration
    """
    return f"https://app.safe.global/transactions/queue?safe=eth:{config.destination}"


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
    - If not dry_run: build transaction, send to Safe
    """
    if config.dry_run:
        await publish_to_stdout(report)
    else:
        transaction = await build_transaction(config, report)
        safe_url = await send_to_safe(config, transaction)
        print(f"Transaction sent to Safe: {safe_url}")
