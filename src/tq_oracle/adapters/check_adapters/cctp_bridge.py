"""CCTP bridge in-flight transaction detection adapter."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

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
    RPC_RATE_LIMIT_DELAY,
    TOKEN_MESSENGER_V2_PROD,
    TOKEN_MESSENGER_V2_TEST,
)

if TYPE_CHECKING:
    from tq_oracle.settings import OracleSettings

logger = logging.getLogger(__name__)


class TransactionIdentity(NamedTuple):
    """Unique identifier for a CCTP bridge transaction.

    Used for matching deposit events on source chain with mint events on destination chain.
    """

    amount: int
    recipient: str


class CCTPBridgeAdapter(BaseCheckAdapter):
    """Detects in-flight CCTP bridging transactions between L1 and Hyperliquid."""

    MESSENGER_ADDRESSES = {
        "testnet": TOKEN_MESSENGER_V2_TEST,
        "mainnet": TOKEN_MESSENGER_V2_PROD,
    }

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self._config = config
        self.testnet = config.testnet

    @property
    def name(self) -> str:
        return "CCTP Bridge In-Flight Detection"

    @staticmethod
    def _extract_address_from_bytes32(w3: AsyncWeb3, bytes32_value: bytes) -> str:
        """Extract 20-byte Ethereum address from bytes32 CCTP field.

        CCTP stores addresses as bytes32 with the actual address in the last 20 bytes.
        This helper extracts and checksums the address for comparison.

        Args:
            w3: Web3 instance for address checksumming
            bytes32_value: The bytes32 value containing the address

        Returns:
            Lowercase checksummed Ethereum address
        """
        return w3.to_checksum_address(bytes32_value[-20:]).lower()

    async def _delay(self) -> None:
        logger.info(f"Sleeping for {RPC_RATE_LIMIT_DELAY}s ...")
        logger.info("tip: 💡 provide custom RPC to speed up checks")
        await asyncio.sleep(RPC_RATE_LIMIT_DELAY)

    async def _cleanup_providers(self, *providers: AsyncWeb3 | None) -> None:
        """Safely disconnect Web3 providers."""
        for provider in providers:
            if provider:
                try:
                    await provider.provider.disconnect()  # type: ignore[union-attr]
                except AttributeError as e:
                    logger.debug(
                        f"Provider disconnect expected (no disconnect method): {e}"
                    )

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

        source_time_multiplier = L1_BLOCK_TIME // source_block_time
        source_blocks_scaled = base_blocks * source_time_multiplier

        max_lookback_multiplier = L1_BLOCK_TIME // HL_BLOCK_TIME
        source_blocks = min(source_blocks_scaled, base_blocks * max_lookback_multiplier)

        time_window_seconds = source_blocks * source_block_time
        dest_blocks = time_window_seconds // dest_block_time

        return (source_blocks, dest_blocks)

    async def run_check(self) -> CheckResult:
        """Check for in-flight CCTP bridging transactions."""
        l1_w3 = None
        hl_w3 = None
        try:
            if not self._config.l1_subvault_address:
                return CheckResult(
                    passed=True,
                    message="Skipping CCTP bridge checks - L1 subvault address not configured",
                    retry_recommended=False,
                )
            if not self._config.hl_subvault_address:
                return CheckResult(
                    passed=True,
                    message="Skipping CCTP bridge checks - HL subvault address not configured",
                    retry_recommended=False,
                )
            logger.debug(f"Connecting to L1 RPC: {self._config.l1_rpc}")
            l1_w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._config.l1_rpc))
            logger.debug(f"Connecting to HL RPC: {self._config.hl_rpc}")
            hl_w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._config.hl_rpc))

            messenger_addr = self.MESSENGER_ADDRESSES[
                "testnet" if self._config.testnet else "mainnet"
            ]

            abi_dir = Path(tq_oracle.__file__).parent / "abis"
            messenger_abi = load_abi(abi_dir / "TokenMessengerV2.json")

            messenger_checksum = l1_w3.to_checksum_address(messenger_addr)
            l1_subvault_checksum = l1_w3.to_checksum_address(
                self._config.l1_subvault_address
            )
            hl_subvault_checksum = hl_w3.to_checksum_address(
                self._config.hl_subvault_address
            )

            l1_messenger = l1_w3.eth.contract(
                address=messenger_checksum, abi=messenger_abi
            )
            hl_messenger = hl_w3.eth.contract(
                address=messenger_checksum, abi=messenger_abi
            )

            l1_to_hl_inflight = await self._check_direction(
                l1_w3,
                hl_w3,
                l1_messenger,
                hl_messenger,
                l1_subvault_checksum,
                hl_subvault_checksum,
                "L1→HL",
                source_block_time=L1_BLOCK_TIME,
                dest_block_time=HL_BLOCK_TIME,
                using_default_rpc=self._config.using_default_rpc,
            )

            if self._config.using_default_rpc:
                await self._delay()

            hl_to_l1_inflight = await self._check_direction(
                hl_w3,
                l1_w3,
                hl_messenger,
                l1_messenger,
                hl_subvault_checksum,
                l1_subvault_checksum,
                "HL→L1",
                source_block_time=HL_BLOCK_TIME,
                dest_block_time=L1_BLOCK_TIME,
                using_default_rpc=self._config.using_default_rpc,
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
        direction: Literal["HL→L1", "L1→HL"],
        source_block_time: int,
        dest_block_time: int,
        using_default_rpc: bool = False,
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
            using_default_rpc: Whether using standard RPC (triggers rate limiting delays)

        Returns:
            Number of in-flight transactions detected
        """
        source_current_block, dest_current_block = await asyncio.gather(
            source_w3.eth.block_number,
            dest_w3.eth.block_number,
        )

        base_lookback = (
            CCTP_RATE_LIMITED_LOOKBACK_BLOCKS
            if self._config.using_default_rpc
            else CCTP_LOOKBACK_BLOCKS
        )

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
        deposit_events = await source_messenger.events.DepositForBurn.get_logs(
            from_block=source_from_block,
            to_block=source_current_block,
            argument_filters={"depositor": source_subvault_address},
        )

        if using_default_rpc:
            await self._delay()

        logger.debug(
            f"{direction}: Querying MintAndWithdraw events from block {dest_from_block} to {dest_current_block} "
            f"with mintRecipient={dest_subvault_address}"
        )
        mint_events = await dest_messenger.events.MintAndWithdraw.get_logs(
            from_block=dest_from_block,
            to_block=dest_current_block,
            argument_filters={
                "mintRecipient": dest_subvault_address,
            },
        )
        logger.info(
            "Fetched %d DepositForBurn events for %s %s",
            len(deposit_events),
            source_subvault_address,
            direction,
        )
        logger.info(
            "Fetched %d MintAndWithdraw events for %s %s",
            len(mint_events),
            dest_subvault_address,
            direction,
        )

        deposited_txs = {
            TransactionIdentity(
                amount=event["args"]["amount"],
                recipient=self._extract_address_from_bytes32(
                    source_w3, event["args"]["mintRecipient"]
                ),
            )
            for event in deposit_events
        }

        minted_txs = {
            TransactionIdentity(
                amount=event["args"]["amount"] + event["args"]["feeCollected"],
                recipient=event["args"]["mintRecipient"].lower(),
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
