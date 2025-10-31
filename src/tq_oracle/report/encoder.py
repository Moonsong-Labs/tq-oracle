"""Transaction encoder for Safe transactions."""

from __future__ import annotations

import logging

from web3 import Web3

from ..abi import load_oracle_abi
from .generator import OracleReport

logger = logging.getLogger(__name__)


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
