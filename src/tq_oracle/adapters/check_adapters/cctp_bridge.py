"""CCTP bridge in-flight transaction detection adapter."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from typing_extensions import Literal
from web3 import AsyncWeb3
from web3.contract import AsyncContract

import tq_oracle
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

    MESSENGER_ADDRESSES = {
        True: TOKEN_MESSENGER_V2_TEST,
        False: TOKEN_MESSENGER_V2_PROD,
    }

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.testnet = config.testnet

    @property
    def name(self) -> str:
        return "CCTP Bridge In-Flight Detection"

    async def _cleanup_providers(self, *providers: AsyncWeb3 | None) -> None:
        """Safely disconnect Web3 providers."""
        for provider in providers:
            if provider:
                try:
                    await provider.provider.disconnect()
                except AttributeError:
                    pass

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

        source_blocks = base_blocks * (L1_BLOCK_TIME // source_block_time)
        source_blocks = min(source_blocks, base_blocks * (L1_BLOCK_TIME // HL_BLOCK_TIME))

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

            messenger_addr = self.MESSENGER_ADDRESSES[config.testnet]

            abi_dir = Path(tq_oracle.__file__).parent / "abis"
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
            await self._cleanup_providers(l1_w3, hl_w3)

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

        deposited_txs = {
            (
                event["args"]["amount"],
                source_w3.to_checksum_address(event["args"]["mintRecipient"][-20:]).lower()
            )
            for event in deposit_events
        }

        minted_txs = {
            (
                event["args"]["amount"] + event["args"]["feeCollected"],
                event["args"]["mintRecipient"].lower()
            )
            for event in mint_events
        }

        inflight_txs = deposited_txs - minted_txs

        if inflight_txs:
            logger.warning(
                f"{direction}: {len(inflight_txs)} in-flight transaction(s) detected"
            )
            logger.debug(f"In-flight transactions: {inflight_txs}")

        return len(inflight_txs)
