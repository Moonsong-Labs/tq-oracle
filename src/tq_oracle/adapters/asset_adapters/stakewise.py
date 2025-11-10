from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Iterable, Optional, cast

import backoff
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError, ProviderConnectionError

from ...abi import (
    load_stakewise_os_token_vault_escrow_abi,
    load_stakewise_vault_abi,
)
from ...constants import STAKEWISE_ADDRESSES
from ...logger import get_logger
from ...settings import OracleSettings
from .base import AssetData, BaseAssetAdapter

logger = get_logger(__name__)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True, slots=True)
class StakeWiseAddressesResolved:
    vault: str
    os_token_vault_escrow: str
    os_token: str


@dataclass(frozen=True, slots=True)
class ExitQueueTicket:
    ticket: int
    shares: int
    receiver: str
    block_number: int
    log_index: int
    timestamp: int
    assets_hint: int | None = None


@dataclass(frozen=True, slots=True)
class AccountState:
    assets: int = 0
    os_shares: int = 0


@dataclass(frozen=True, slots=True)
class ExitExposure:
    staked_eth: int = 0
    eth_in_queue: int = 0
    eth_ready: int = 0
    os_shares_liability: int = 0
    escrow_os_shares: int = 0
    ticket_count: int = 0

    @property
    def eth_collateral(self) -> int:
        return self.staked_eth + self.eth_in_queue + self.eth_ready


class StakeWiseAdapter(BaseAssetAdapter):
    """Adapter for StakeWise vault positions (direct staking only)."""

    def __init__(
        self,
        config: OracleSettings,
        *,
        vault_address: str | None = None,
    ):
        super().__init__(config)

        self.w3 = self._build_web3(config.vault_rpc_required)

        resolved = self._resolve_addresses(config, vault_address)

        self.block_identifier = config.block_number_required
        self.eth_asset = self._resolve_eth_asset(config)
        self.os_token_address = self.w3.to_checksum_address(resolved.os_token)
        self.os_token_vault_escrow_address = self.w3.to_checksum_address(
            resolved.os_token_vault_escrow
        )
        self.vault_address = self.w3.to_checksum_address(resolved.vault)

        self.vault = self._build_contract(
            self.vault_address, load_stakewise_vault_abi()
        )
        self.os_token_vault_escrow: Contract = self._build_contract(
            self.os_token_vault_escrow_address,
            load_stakewise_os_token_vault_escrow_abi(),
        )

        self._exit_log_chunk = 200
        self._exit_queue_start_block = config.stakewise_exit_queue_start_block or 0
        self._rpc_sem = asyncio.Semaphore(getattr(config, "max_calls", 5))
        self._rpc_delay = getattr(config, "rpc_delay", 0.15)
        self._rpc_jitter = getattr(config, "rpc_jitter", 0.10)
        self._block_timestamp_cache: dict[int, int] = {}

        # Vault versions emit either ExitQueueEntered or V2ExitQueueEntered.
        self._exit_events: list = [self.vault.events.ExitQueueEntered()]
        v2_event = getattr(self.vault.events, "V2ExitQueueEntered", None)
        if callable(v2_event):
            self._exit_events.append(v2_event())

    @property
    def adapter_name(self) -> str:
        return "stakewise"

    @backoff.on_exception(
        backoff.expo,
        (ProviderConnectionError,),
        max_time=30,
        jitter=backoff.full_jitter,
    )
    async def _rpc(self, fn, *args, **kwargs):
        async with self._rpc_sem:
            try:
                return await asyncio.to_thread(fn, *args, **kwargs)
            finally:
                delay = self._rpc_delay + random.random() * self._rpc_jitter
                if delay > 0:
                    await asyncio.sleep(delay)

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        user = self.w3.to_checksum_address(subvault_address)
        logger.info(
            "StakeWise adapter collecting balances — user=%s block=%s",
            user,
            self.block_identifier,
        )

        user_state = await self._fetch_account_state(user)
        tickets = await self._scan_exit_queue_tickets(user)
        exposure = await self._compute_exit_exposure(user_state, tickets)

        assets: list[AssetData] = []
        self._append_asset(assets, self.eth_asset, exposure.eth_collateral)
        if exposure.os_shares_liability:
            self._append_asset(
                assets, self.os_token_address, -exposure.os_shares_liability
            )

        self._log_summary(user, exposure)
        return assets

    @staticmethod
    def _build_web3(rpc_url: str) -> Web3:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {rpc_url}")
        return w3

    @staticmethod
    def _resolve_eth_asset(config: OracleSettings) -> str:
        eth_asset = config.assets.get("ETH")
        if eth_asset is None:
            raise ValueError("ETH address must be configured for StakeWise adapter")
        return eth_asset

    def _resolve_addresses(
        self, config: OracleSettings, override_vault: Optional[str]
    ) -> StakeWiseAddressesResolved:
        defaults = STAKEWISE_ADDRESSES.get(config.network.value) or {}

        values = {
            "stakewise_vault_address": override_vault
            or config.stakewise_vault_address
            or defaults.get("vault"),
            "stakewise_os_token_vault_escrow": config.stakewise_os_token_vault_escrow
            or defaults.get("os_token_vault_escrow"),
            "stakewise_os_token_address": config.stakewise_os_token_address
            or defaults.get("os_token"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(
                "Missing StakeWise configuration values: "
                f"{', '.join(missing)}. Provide them via configuration or ensure defaults exist for network '{config.network.value}'."
            )

        return StakeWiseAddressesResolved(
            vault=cast(str, values["stakewise_vault_address"]),
            os_token_vault_escrow=cast(str, values["stakewise_os_token_vault_escrow"]),
            os_token=cast(str, values["stakewise_os_token_address"]),
        )

    def _build_contract(self, address: str, abi: Iterable[dict]) -> Contract:
        checksum = self.w3.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum, abi=list(abi))

    async def _fetch_account_state(self, account: str) -> AccountState:
        shares, os_shares = await asyncio.gather(
            self._rpc(
                self.vault.functions.getShares(account).call,
                block_identifier=self.block_identifier,
            ),
            self._rpc(
                self.vault.functions.osTokenPositions(account).call,
                block_identifier=self.block_identifier,
            ),
        )
        assets = (
            0
            if not shares
            else await self._rpc(
                self.vault.functions.convertToAssets(shares).call,
                block_identifier=self.block_identifier,
            )
        )
        return AccountState(assets=int(assets), os_shares=int(os_shares))

    async def _scan_exit_queue_tickets(self, user: str) -> list[ExitQueueTicket]:
        if not self._exit_events:
            return []

        tickets: dict[int, ExitQueueTicket] = {}
        to_block = self.block_identifier
        min_block = max(self._exit_queue_start_block, 0)

        while to_block >= min_block:
            from_block = max(min_block, to_block - self._exit_log_chunk + 1)
            logger.debug(
                "StakeWise exit log scan — user=%s chunk=[%d,%d]",
                user,
                from_block,
                to_block,
            )
            for event in self._exit_events:
                logs = await self._get_exit_logs(event, user, from_block, to_block)
                for log in logs:
                    args = log["args"]
                    ticket_id = int(args["positionTicket"])
                    shares = int(args["shares"])
                    receiver = self.w3.to_checksum_address(args["receiver"])
                    block_number = int(log["blockNumber"])
                    log_index = int(log["logIndex"])
                    timestamp = await self._resolve_block_timestamp(block_number)
                    assets_value = args.get("assets")
                    assets_hint = (
                        int(assets_value) if assets_value is not None else None
                    )

                    existing = tickets.get(ticket_id)
                    if existing and (
                        existing.block_number > block_number
                        or (
                            existing.block_number == block_number
                            and existing.log_index >= log_index
                        )
                    ):
                        continue

                    tickets[ticket_id] = ExitQueueTicket(
                        ticket=ticket_id,
                        shares=shares,
                        receiver=receiver,
                        block_number=block_number,
                        log_index=log_index,
                        timestamp=timestamp,
                        assets_hint=assets_hint,
                    )
            to_block = from_block - 1

        ordered = sorted(tickets.values(), key=lambda t: (t.block_number, t.log_index))
        logger.info(
            "StakeWise exit queue scan completed — user=%s tickets=%d",
            user,
            len(ordered),
        )
        return ordered

    async def _get_exit_logs(self, event, user: str, from_block: int, to_block: int):
        try:
            return await self._rpc(
                event.get_logs,
                fromBlock=from_block,
                toBlock=to_block,
                argument_filters={"owner": user},
            )
        except ValueError as exc:  # pragma: no cover - provider variance
            event_name = getattr(event, "abi", {}).get("name", "unknown")
            logger.warning(
                "StakeWise exit log query failed — event=%s user=%s chunk=[%d,%d] err=%s",
                event_name,
                user,
                from_block,
                to_block,
                exc,
            )
            return []

    async def _resolve_block_timestamp(self, block_number: int) -> int:
        cached = self._block_timestamp_cache.get(block_number)
        if cached is not None:
            return cached
        block = await self._rpc(self.w3.eth.get_block, block_number)
        timestamp = int(block["timestamp"])
        self._block_timestamp_cache[block_number] = timestamp
        return timestamp

    async def _compute_exit_exposure(
        self,
        user_state: AccountState,
        tickets: list[ExitQueueTicket],
    ) -> ExitExposure:
        eth_in_queue = 0
        eth_ready = 0
        escrow_os_shares = 0

        for ticket in tickets:
            initial_assets = ticket.assets_hint
            if initial_assets is None:
                initial_assets = await self._rpc(
                    self.vault.functions.convertToAssets(ticket.shares).call,
                    block_identifier=self.block_identifier,
                )
            initial_assets = int(initial_assets)

            if ticket.receiver == self.os_token_vault_escrow_address:
                escrow_state = await self._fetch_escrow_state(ticket.ticket)
                if escrow_state is None:
                    continue
                os_shares, exited_assets = escrow_state
                escrow_os_shares += os_shares
                eth_ready += exited_assets
                continue

            exit_queue_index = await self._fetch_exit_queue_index(ticket.ticket)
            if exit_queue_index is None or exit_queue_index < 0:
                eth_ready += initial_assets
                continue

            exited_assets = await self._calculate_exited_assets(
                ticket.receiver, ticket.ticket, ticket.timestamp, exit_queue_index
            )
            exited_assets = min(exited_assets, initial_assets)
            remaining = max(initial_assets - exited_assets, 0)
            eth_ready += exited_assets
            eth_in_queue += remaining

        os_liabilities = user_state.os_shares + escrow_os_shares
        return ExitExposure(
            staked_eth=user_state.assets,
            eth_in_queue=eth_in_queue,
            eth_ready=eth_ready,
            os_shares_liability=os_liabilities,
            escrow_os_shares=escrow_os_shares,
            ticket_count=len(tickets),
        )

    async def _fetch_exit_queue_index(self, ticket: int) -> int | None:
        try:
            index = await self._rpc(
                self.vault.functions.getExitQueueIndex(ticket).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            logger.warning(
                "StakeWise exit queue index lookup failed — ticket=%d",
                ticket,
            )
            return None
        return int(index)

    async def _calculate_exited_assets(
        self, receiver: str, ticket: int, timestamp: int, exit_queue_index: int
    ) -> int:
        try:
            _, _, exit_assets = await self._rpc(
                self.vault.functions.calculateExitedAssets(
                    receiver,
                    ticket,
                    timestamp,
                    exit_queue_index,
                ).call,
                block_identifier=self.block_identifier,
            )
            return int(exit_assets)
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            logger.debug(
                "StakeWise calculateExitedAssets failed — receiver=%s ticket=%d index=%d",
                receiver,
                ticket,
                exit_queue_index,
            )
            return 0

    async def _fetch_escrow_state(self, ticket: int) -> tuple[int, int] | None:
        try:
            owner, exited_assets, os_token_shares = await self._rpc(
                self.os_token_vault_escrow.functions.getPosition(
                    self.vault_address, ticket
                ).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            logger.warning(
                "StakeWise exit escrow lookup failed — ticket=%d",
                ticket,
            )
            return None

        if owner and owner != ZERO_ADDRESS:
            try:
                resolved_owner = self.w3.to_checksum_address(owner)
            except ValueError:  # pragma: no cover - corrupted response
                resolved_owner = owner
            if resolved_owner.lower() != self.os_token_vault_escrow_address.lower():
                logger.warning(
                    "StakeWise exit ticket owner mismatch — expected escrow=%s owner=%s ticket=%d",
                    self.os_token_vault_escrow_address,
                    resolved_owner,
                    ticket,
                )
                return None

        return int(os_token_shares), int(exited_assets)

    @staticmethod
    def _append_asset(assets: list[AssetData], address: str, amount: int) -> None:
        if amount:
            assets.append(AssetData(asset_address=address, amount=amount))

    def _log_summary(self, user: str, exposure: ExitExposure) -> None:
        logger.debug(
            "StakeWise summary for %s — eth_collateral=%d (staked=%d, queue=%d, ready=%d), os_liabilities=%d (escrow_shares=%d) tickets=%d",
            user,
            exposure.eth_collateral,
            exposure.staked_eth,
            exposure.eth_in_queue,
            exposure.eth_ready,
            exposure.os_shares_liability,
            exposure.escrow_os_shares,
            exposure.ticket_count,
        )
