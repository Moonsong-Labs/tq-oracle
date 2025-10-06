"""Transaction builder for encoding Safe transactions."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from web3 import Web3

if TYPE_CHECKING:
    from ..report.generator import OracleReport

logger = logging.getLogger(__name__)

ABI_PATH = (
    Path(__file__).parent.parent.parent.parent / "contracts" / "abis" / "IOracle.json"
)


def load_oracle_abi() -> list[dict]:
    """Load IOracle ABI from contracts/abis/IOracle.json.

    Returns:
        ABI as a list of dictionaries

    Raises:
        FileNotFoundError: If ABI file doesn't exist
        json.JSONDecodeError: If ABI file is malformed
    """
    with open(ABI_PATH) as f:
        data = json.load(f)
        return data["abi"]


def encode_submit_reports(
    oracle_address: str,
    report: OracleReport,
) -> tuple[str, bytes]:
    """Encode submitReports() transaction data.

    Args:
        oracle_address: IOracle contract address
        report: Oracle report with final_prices dict

    Returns:
        Tuple of (to_address, encoded_calldata)

    The submitReports function expects:
        struct Report[] reports where Report = (address asset, uint224 priceD18)
    """
    w3 = Web3()
    abi = load_oracle_abi()

    checksum_address = w3.to_checksum_address(oracle_address)
    contract = w3.eth.contract(address=checksum_address, abi=abi)

    # Convert report.final_prices dict to list of tuples
    # Format: [(asset_address, price_d18), ...]
    reports_array = [
        (asset_addr, price_d18) for asset_addr, price_d18 in report.final_prices.items()
    ]

    logger.info("Encoding submitReports() with %d report(s):", len(reports_array))
    for asset_addr, price_d18 in reports_array:
        price_decimal = price_d18 / 10**18
        logger.info(
            "  - Asset: %s, Price: %d D18 (%.6f)", asset_addr, price_d18, price_decimal
        )

    calldata_hex = contract.encode_abi(
        abi_element_identifier="submitReports",
        args=[reports_array],
    )

    calldata = bytes.fromhex(calldata_hex.removeprefix("0x"))

    return (oracle_address, calldata)
