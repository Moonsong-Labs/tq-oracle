#!/usr/bin/env python3
"""Standalone test script for CCTP bridge in-flight transaction detection."""

from __future__ import annotations

import asyncio
import sys
from argparse import ArgumentParser

from tq_oracle.adapters.check_adapters.cctp_bridge import CCTPBridgeAdapter
from tq_oracle.config import OracleCLIConfig
from tq_oracle.constants import (
    DEFAULT_MAINNET_RPC_URL,
    DEFAULT_SEPOLIA_RPC_URL,
    HL_PROD_EVM_RPC,
    HL_TEST_EVM_RPC,
)
from tq_oracle.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


async def test_cctp_bridge(
    l1_subvault_address: str,
    hl_subvault_address: str,
    testnet: bool = False,
    l1_rpc: str | None = None,
    hl_rpc: str | None = None,
) -> int:
    """Test CCTP bridge in-flight transaction detection.

    Args:
        l1_subvault_address: L1 subvault address to monitor
        hl_subvault_address: Hyperliquid subvault address to monitor
        testnet: Whether to use testnet (default: False for mainnet)
        l1_rpc: Custom L1 RPC URL (optional, defaults based on testnet flag)
        hl_rpc: Custom Hyperliquid RPC URL (optional, defaults based on testnet flag)
    """
    using_default_rpc = (l1_rpc is None or hl_rpc is None)

    if l1_rpc is None:
        l1_rpc = DEFAULT_SEPOLIA_RPC_URL if testnet else DEFAULT_MAINNET_RPC_URL

    if hl_rpc is None:
        hl_rpc = HL_TEST_EVM_RPC if testnet else HL_PROD_EVM_RPC

    config = OracleCLIConfig(
        vault_address="",
        oracle_helper_address="",
        l1_rpc=l1_rpc,
        l1_subvault_address=l1_subvault_address,
        safe_address=None,
        hl_rpc=hl_rpc,
        hl_subvault_address=hl_subvault_address,
        testnet=testnet,
        dry_run=True,
        safe_txn_srvc_api_key=None,
        private_key=None,
        ignore_empty_vault=True,
        using_default_rpc=using_default_rpc,
    )

    logger.info("=== CCTP Bridge In-Flight Transaction Detection Test ===")
    logger.info(f"L1 Subvault: {l1_subvault_address}")
    logger.info(f"HL Subvault: {hl_subvault_address}")
    logger.info(f"Network: {'Testnet' if testnet else 'Mainnet'}")
    logger.info(f"L1 RPC: {l1_rpc}")
    logger.info(f"HL RPC: {hl_rpc}")
    logger.info("=" * 60)

    adapter = CCTPBridgeAdapter(config)
    result = await adapter.run_check()

    logger.info("\n=== Results ===")
    logger.info(f"Check Passed: {result.passed}")
    logger.info(f"Message: {result.message}")
    logger.info(f"Retry Recommended: {result.retry_recommended}")
    logger.info("=" * 60)

    return 0 if result.passed else 1


def main() -> int:
    """Parse arguments and run the test."""
    parser = ArgumentParser(
        description="Test CCTP bridge in-flight transaction detection"
    )
    parser.add_argument(
        "l1_subvault_address",
        help="L1 subvault address to monitor",
    )
    parser.add_argument(
        "hl_subvault_address",
        help="Hyperliquid subvault address to monitor",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use testnet instead of mainnet",
    )
    parser.add_argument(
        "--l1-rpc",
        help="Custom L1 RPC URL (optional)",
    )
    parser.add_argument(
        "--hl-rpc",
        help="Custom Hyperliquid RPC URL (optional)",
    )

    args = parser.parse_args()

    try:
        exit_code = asyncio.run(
            test_cctp_bridge(
                l1_subvault_address=args.l1_subvault_address,
                hl_subvault_address=args.hl_subvault_address,
                testnet=args.testnet,
                l1_rpc=args.l1_rpc,
                hl_rpc=args.hl_rpc,
            )
        )
        return exit_code
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
