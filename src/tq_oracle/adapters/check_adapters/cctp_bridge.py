"""CCTP bridge in-flight transaction detection adapter."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from typing_extensions import Literal
from web3 import AsyncWeb3
from web3.contract import AsyncContract

from tq_oracle.abi import load_abi
from tq_oracle.adapters.check_adapters.base import BaseCheckAdapter, CheckResult
from tq_oracle.constants import (
    CCTP_LOOKBACK_BLOCKS,
    CCTP_RATE_LIMITED_LOOKBACK_BLOCKS,
    HL_BLOCK_TIME,
    L1_BLOCK_TIME,
    TOKEN_MESSENGER_V2_PROD,
    TOKEN_MESSENGER_V2_TEST,
)

if TYPE_CHECKING:
    from tq_oracle.config import OracleCLIConfig

logger = logging.getLogger(__name__)


class CCTPBridgeAdapter(BaseCheckAdapter):
    """Detects in-flight CCTP bridging transactions between L1 and Hyperliquid."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.testnet = config.testnet

    @property
    def name(self) -> str:
        return "CCTP Bridge In-Flight Detection"

    def _calculate_scaled_blocks(
        self, base_blocks: int, source_block_time: int, dest_block_time: int
    ) -> tuple[int, int]:
        """Calculate scaled lookback blocks for source and destination chains.

        Args:
            base_blocks: Base lookback blocks (calibrated for L1)
            source_block_time: Block time of source chain in seconds
            dest_block_time: Block time of destination chain in seconds

        Returns:
            Tuple of (source_blocks, dest_blocks) ensuring same time window
        """
        if source_block_time == dest_block_time:
            return (base_blocks, base_blocks)

        # Scale source blocks based on its block time relative to L1
        # e.g., HL (1s) gets 12x more blocks than ETH (12s) for same time window
        source_blocks = base_blocks * (L1_BLOCK_TIME // source_block_time)
        # Cap to ensure we don't exceed the base lookback limit
        source_blocks = min(source_blocks, base_blocks * (L1_BLOCK_TIME // HL_BLOCK_TIME))

        # Calculate destination blocks to match the same time window
        time_window_seconds = source_blocks * source_block_time
        dest_blocks = time_window_seconds // dest_block_time

        return (source_blocks, dest_blocks)

    async def run_check(self) -> CheckResult:
        """Check for in-flight CCTP bridging transactions."""
        l1_w3 = None
        hl_w3 = None
        try:
            config = cast("OracleCLIConfig", self.config)

            if not config.l1_subvault_address:
                return CheckResult(
                    passed=False,
                    message="L1 subvault address is required for CCTP bridge checks",
                    retry_recommended=False,
                )
            if not config.hl_subvault_address:
                return CheckResult(
                    passed=False,
                    message="HL subvault address is required for CCTP bridge checks",
                    retry_recommended=False,
                )
            logger.debug(f"Connecting to L1 RPC: {config.l1_rpc}")
            l1_w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(config.l1_rpc))
            logger.debug(f"Connecting to HL RPC: {config.hl_rpc}")
            hl_w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(config.hl_rpc))

            if config.testnet:
                messenger_addr = TOKEN_MESSENGER_V2_TEST
            else:
                messenger_addr = TOKEN_MESSENGER_V2_PROD

            abi_dir = Path(__file__).parent.parent.parent / "abis"
            messenger_abi = load_abi(abi_dir / "TokenMessengerV2.json")

            messenger_checksum = l1_w3.to_checksum_address(messenger_addr)
            l1_subvault_checksum = l1_w3.to_checksum_address(config.l1_subvault_address)
            hl_subvault_checksum = hl_w3.to_checksum_address(config.hl_subvault_address)

            l1_messenger = l1_w3.eth.contract(
                address=messenger_checksum, abi=messenger_abi
            )
            hl_messenger = hl_w3.eth.contract(
                address=messenger_checksum, abi=messenger_abi
            )

            l1_to_hl_inflight, hl_to_l1_inflight = await asyncio.gather(
                self._check_direction(
                    l1_w3,
                    hl_w3,
                    l1_messenger,
                    hl_messenger,
                    l1_subvault_checksum,
                    hl_subvault_checksum,
                    "L1→HL",
                    source_block_time=L1_BLOCK_TIME,
                    dest_block_time=HL_BLOCK_TIME,
                ),
                self._check_direction(
                    hl_w3,
                    l1_w3,
                    hl_messenger,
                    l1_messenger,
                    hl_subvault_checksum,
                    l1_subvault_checksum,
                    "HL→L1",
                    source_block_time=HL_BLOCK_TIME,
                    dest_block_time=L1_BLOCK_TIME,
                ),
            )

            total_inflight = l1_to_hl_inflight + hl_to_l1_inflight

            if total_inflight > 0:
                return CheckResult(
                    passed=False,
                    message=f"Found {total_inflight} in-flight CCTP bridging transaction(s)",
                    retry_recommended=True,
                )

            return CheckResult(
                passed=True,
                message="No in-flight CCTP bridging transactions detected",
                retry_recommended=False,
            )

        except Exception as e:
            logger.error(f"Error checking CCTP bridge: {e}")
            return CheckResult(
                passed=False,
                message=f"Error checking CCTP bridge: {str(e)}",
                retry_recommended=False,
            )
        finally:
            if l1_w3 and hasattr(l1_w3, 'provider') and hasattr(l1_w3.provider, 'disconnect'):
                await l1_w3.provider.disconnect()
            if hl_w3 and hasattr(hl_w3, 'provider') and hasattr(hl_w3.provider, 'disconnect'):
                await hl_w3.provider.disconnect()

    async def _check_direction(
        self,
        source_w3: AsyncWeb3,
        dest_w3: AsyncWeb3,
        source_messenger: AsyncContract,
        dest_messenger: AsyncContract,
        source_subvault_address: str,
        dest_subvault_address: str,
        direction: Literal['HL→L1', 'L1→HL'],
        source_block_time: int,
        dest_block_time: int,
    ) -> int:
        """Check for in-flight transactions in one direction.

        Args:
            source_w3: Web3 instance for source chain
            dest_w3: Web3 instance for destination chain
            source_messenger: TokenMessenger contract on source chain
            dest_messenger: TokenMessenger contract on destination chain
            source_subvault_address: Checksummed subvault address on source chain (depositor filter)
            dest_subvault_address: Checksummed subvault address on destination chain (mintRecipient filter)
            direction: Human-readable direction label for logging
            source_block_time: Block time of source chain in seconds
            dest_block_time: Block time of destination chain in seconds

        Returns:
            Number of in-flight transactions detected
        """
        source_current_block, dest_current_block = await asyncio.gather(
            source_w3.eth.block_number,
            dest_w3.eth.block_number,
        )

        config = cast("OracleCLIConfig", self.config)
        base_lookback = CCTP_RATE_LIMITED_LOOKBACK_BLOCKS if config.using_default_rpc else CCTP_LOOKBACK_BLOCKS

        # Calculate scaled blocks for both chains
        logger.debug(f"Calculating lookback blocks for {direction} direction")
        source_lookback, dest_lookback = self._calculate_scaled_blocks(
            base_lookback, source_block_time, dest_block_time
        )

        source_from_block = source_current_block - source_lookback + 1
        dest_from_block = dest_current_block - dest_lookback + 1

        logger.debug(
            f"{direction}: Source lookback={source_lookback} blocks ({source_lookback * source_block_time}s), "
            f"Dest lookback={dest_lookback} blocks ({dest_lookback * dest_block_time}s)"
        )

        logger.debug(
            f"{direction}: Querying DepositForBurn events from block {source_from_block} to {source_current_block} "
            f"with depositor={source_subvault_address}"
        )
        logger.debug(
            f"{direction}: Querying MintAndWithdraw events from block {dest_from_block} to {dest_current_block} "
            f"with mintRecipient={dest_subvault_address}"
        )

        deposit_events_task = source_messenger.events.DepositForBurn.get_logs(
            from_block=source_from_block,
            to_block=source_current_block,
            argument_filters={"depositor": source_subvault_address},
        )
        # Note: We don't filter by mintToken because USDC has different addresses on each chain
        # (e.g., Sepolia USDC vs Hyperliquid USDC). Filtering by mintRecipient is sufficient
        # since it's our specific subvault address.
        mint_events_task = dest_messenger.events.MintAndWithdraw.get_logs(
            from_block=dest_from_block,
            to_block=dest_current_block,
            argument_filters={
                "mintRecipient": dest_subvault_address,
            },
        )

        deposit_events, mint_events = await asyncio.gather(
            deposit_events_task, mint_events_task
        )
        logger.debug("Fetched %d DepositForBurn events for %s %s", len(deposit_events), source_subvault_address, direction)
        logger.debug("Fetched %d MintAndWithdraw events for %s %s", len(mint_events), dest_subvault_address, direction)

        # Create sets of (amount, recipient) tuples for matching
        # DepositForBurn: amount is burned amount, mintRecipient is bytes32
        deposited_txs = set()
        for event in deposit_events:
            amount = event["args"]["amount"]
            # Convert bytes32 mintRecipient to address (last 20 bytes)
            mint_recipient_bytes32 = event["args"]["mintRecipient"]
            # Use web3 utility for robust conversion from bytes32 to address
            mint_recipient_addr = source_w3.to_checksum_address(mint_recipient_bytes32[-20:]).lower()
            deposited_txs.add((amount, mint_recipient_addr))

        # MintAndWithdraw: amount minted (excluding fees)
        # Total deposited = amount + feeCollected
        minted_txs = set()
        for event in mint_events:
            amount = event["args"]["amount"]
            fee_collected = event["args"]["feeCollected"]
            total_amount = amount + fee_collected
            mint_recipient = event["args"]["mintRecipient"].lower()
            minted_txs.add((total_amount, mint_recipient))

        # Find deposits that haven't been minted yet
        inflight_txs = deposited_txs - minted_txs

        if inflight_txs:
            logger.warning(
                f"{direction}: {len(inflight_txs)} in-flight transaction(s) detected"
            )
            logger.debug(f"In-flight transactions: {inflight_txs}")

        return len(inflight_txs)
