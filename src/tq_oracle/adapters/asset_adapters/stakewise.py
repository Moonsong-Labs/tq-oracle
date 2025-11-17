from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, TypedDict, cast

import backoff
import requests
from web3 import Web3
from web3.contract import Contract
from web3.contract.contract import ContractEvent
from web3.exceptions import ContractLogicError, ProviderConnectionError
from web3.types import EventData

from eth_typing import HexStr

from ...abi import (
    load_stakewise_os_token_vault_escrow_abi,
    load_stakewise_vault_abi,
)
from ...constants import (
    STAKEWISE_ADDRESSES,
    STAKEWISE_EXIT_LOG_CHUNK,
    STAKEWISE_EXIT_MAX_LOOKBACK_BLOCKS,
)
from ...logger import get_logger
from ...settings import OracleSettings
from .base import AssetData, BaseAssetAdapter

logger = get_logger(__name__)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
STAKEWISE_EXIT_LOG_CHUNK = 1000

ETHERSCAN_DEFAULT_API_URL = "https://api.etherscan.io/v2/api"


@dataclass(frozen=True, slots=True)
class StakeWiseAddressesResolved:
    vault: str
    os_token_vault_escrow: str
    os_token: str


class EtherscanLogsResult(TypedDict, total=False):
    address: str
    topics: list[str]
    data: str
    blockNumber: str
    blockHash: str
    timeStamp: str
    gasPrice: str
    gasUsed: str
    logIndex: str
    transactionHash: str
    transactionIndex: str


class EtherscanLogsResponse(TypedDict):
    status: str
    message: str
    result: list[EtherscanLogsResult] | str


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
    eth_claimable: int = 0
    os_shares_liability: int = 0
    escrow_os_shares: int = 0
    ticket_count: int = 0

    @property
    def eth_collateral(self) -> int:
        return self.staked_eth + self.eth_in_queue + self.eth_claimable


@dataclass(frozen=True, slots=True)
class StakewiseVaultContext:
    address: str
    contract: Contract
    exit_events: list[ContractEvent]


class StakeWiseAdapter(BaseAssetAdapter):
    """Adapter for StakeWise vault positions (direct staking only)."""

    def __init__(
        self,
        config: OracleSettings,
        *,
        stakewise_vault_address: str | None = None,
        stakewise_vault_addresses: list[str] | None = None,
        etherscan_api_key: str | None = None,
        etherscan_page_size: int | None = None,
    ):
        super().__init__(config)

        self.w3 = self._build_web3(config.vault_rpc_required)

        stakewise_defaults = config.adapters.stakewise
        default_vaults = stakewise_defaults.stakewise_vault_addresses
        fallback_single = stakewise_vault_address or (
            default_vaults[0] if default_vaults else None
        )
        resolved = self._resolve_addresses(config, fallback_single)
        self._etherscan_chain_id = config.chain_id

        self.block_identifier = config.block_number_required
        self.eth_asset = self._resolve_eth_asset(config)
        self.os_token_address = self.w3.to_checksum_address(resolved.os_token)
        self.os_token_vault_escrow_address = self.w3.to_checksum_address(
            resolved.os_token_vault_escrow
        )
        resolved_vaults = stakewise_vault_addresses or default_vaults
        if not resolved_vaults:
            resolved_vaults = [stakewise_vault_address or resolved.vault]
        if not resolved_vaults:
            raise ValueError("StakeWise adapter requires at least one vault address")

        self.vault_contexts: list[StakewiseVaultContext] = [
            self._build_vault_context(address) for address in resolved_vaults
        ]
        self.vault_address = self.vault_contexts[0].address
        self.os_token_vault_escrow: Contract = self._build_contract(
            self.os_token_vault_escrow_address,
            load_stakewise_os_token_vault_escrow_abi(),
        )

        self._rpc_sem = asyncio.Semaphore(getattr(config, "max_calls", 5))
        self._rpc_delay = getattr(config, "rpc_delay", 0.15)
        self._rpc_jitter = getattr(config, "rpc_jitter", 0.10)
        self._block_timestamp_cache: dict[int, int] = {}
        self._etherscan_session = requests.Session()
        (
            self._etherscan_api_url,
            self._etherscan_api_key,
            self._etherscan_page_size,
        ) = self._resolve_etherscan_config(
            stakewise_defaults,
            STAKEWISE_EXIT_LOG_CHUNK,
            api_key_override=etherscan_api_key,
            page_size_override=etherscan_page_size,
        )

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

        total_staked = 0
        total_queue = 0
        total_claimable = 0
        total_os_liabilities = 0
        total_escrow_shares = 0
        total_tickets = 0

        for context in self.vault_contexts:
            user_state = await self._fetch_account_state(context.contract, user)
            tickets = await self._scan_exit_queue_tickets(context, user)
            exposure = await self._compute_exit_exposure(context, user_state, tickets)

            total_staked += exposure.staked_eth
            total_queue += exposure.eth_in_queue
            total_claimable += exposure.eth_claimable
            total_os_liabilities += exposure.os_shares_liability
            total_escrow_shares += exposure.escrow_os_shares
            total_tickets += exposure.ticket_count

        aggregated = ExitExposure(
            staked_eth=total_staked,
            eth_in_queue=total_queue,
            eth_claimable=total_claimable,
            os_shares_liability=total_os_liabilities,
            escrow_os_shares=total_escrow_shares,
            ticket_count=total_tickets,
        )

        assets: list[AssetData] = []
        self._append_asset(assets, self.eth_asset, aggregated.eth_collateral)
        if aggregated.os_shares_liability:
            self._append_asset(
                assets, self.os_token_address, -aggregated.os_shares_liability
            )

        self._log_summary(user, aggregated)
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
            "stakewise_vault_address": override_vault or defaults.get("vault"),
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

    def _build_vault_context(self, address: str) -> StakewiseVaultContext:
        contract = self._build_contract(address, load_stakewise_vault_abi())
        exit_events: list[ContractEvent] = [contract.events.ExitQueueEntered()]
        v2_event = getattr(contract.events, "V2ExitQueueEntered", None)
        if callable(v2_event):
            exit_events.append(cast(ContractEvent, v2_event()))
        return StakewiseVaultContext(
            address=self.w3.to_checksum_address(address),
            contract=contract,
            exit_events=exit_events,
        )

    def _resolve_etherscan_config(
        self,
        defaults,
        chunk_size: int,
        *,
        api_key_override: str | None = None,
        page_size_override: int | None = None,
    ) -> tuple[str | None, str | None, int]:
        api_key = api_key_override or getattr(defaults, "etherscan_api_key", None)
        if not api_key:
            return None, None, 0

        if page_size_override is not None:
            page_size = page_size_override
        else:
            page_size = (
                getattr(defaults, "etherscan_page_size", chunk_size) or chunk_size
            )

        return ETHERSCAN_DEFAULT_API_URL, api_key, max(1, page_size)

    async def _fetch_account_state(
        self, vault_contract: Contract, account: str
    ) -> AccountState:
        shares, os_shares = await asyncio.gather(
            self._rpc(
                vault_contract.functions.getShares(account).call,
                block_identifier=self.block_identifier,
            ),
            self._rpc(
                vault_contract.functions.osTokenPositions(account).call,
                block_identifier=self.block_identifier,
            ),
        )
        assets = (
            0
            if not shares
            else await self._rpc(
                vault_contract.functions.convertToAssets(shares).call,
                block_identifier=self.block_identifier,
            )
        )
        return AccountState(assets=int(assets), os_shares=int(os_shares))

    async def _scan_exit_queue_tickets(
        self, context: StakewiseVaultContext, user: str
    ) -> list[ExitQueueTicket]:
        if not context.exit_events:
            return []

        tickets: dict[int, ExitQueueTicket] = {}
        min_block = self._resolve_min_block()
        to_block = self.block_identifier
        logger.info(
            f"StakeWise exit queue scan start for {context.address}, this might take some time..."
        )

        seen_logs: set[tuple[str, int]] = set()
        for event in context.exit_events:
            for filter_field in ("owner", "receiver"):
                if not self._event_supports_filter(event, filter_field):
                    continue
                logs = await self._get_exit_logs(
                    context,
                    event,
                    filter_field,
                    user,
                    min_block,
                    to_block,
                )
                for log in logs:
                    log_index = int(log["logIndex"])
                    tx_value = log.get("transactionHash")
                    if isinstance(tx_value, (bytes, bytearray)):
                        tx_hash_str = bytes(tx_value).hex()
                    elif hasattr(tx_value, "hex") and callable(tx_value.hex):
                        tx_hash_str = tx_value.hex()
                    else:
                        tx_hash_str = str(tx_value)
                    if not tx_hash_str or tx_hash_str == "None":
                        tx_hash_str = f"{log.get('blockNumber')}:{log_index}"
                    log_key: tuple[str, int] = (tx_hash_str, log_index)
                    if log_key in seen_logs:
                        continue
                    seen_logs.add(log_key)

                    args = log["args"]
                    ticket_id = int(args["positionTicket"])
                    block_number = int(log["blockNumber"])

                    existing = tickets.get(ticket_id)
                    if existing and not (
                        block_number > existing.block_number
                        or (
                            block_number == existing.block_number
                            and log_index > existing.log_index
                        )
                    ):
                        continue

                    timestamp = await self._resolve_block_timestamp(block_number)
                    assets_value = args.get("assets")
                    tickets[ticket_id] = ExitQueueTicket(
                        ticket=ticket_id,
                        shares=int(args["shares"]),
                        receiver=self.w3.to_checksum_address(args["receiver"]),
                        block_number=block_number,
                        log_index=log_index,
                        timestamp=timestamp,
                        assets_hint=None if assets_value is None else int(assets_value),
                    )

        ordered = sorted(tickets.values(), key=lambda t: (t.block_number, t.log_index))
        logger.info(
            "StakeWise exit queue scan completed — vault=%s user=%s tickets=%d iterations=%d",
            context.address,
            user,
            len(ordered),
            1,
        )
        return ordered

    @staticmethod
    def _event_supports_filter(event: ContractEvent, field_name: str) -> bool:
        abi = getattr(event, "abi", None)
        if not abi:
            return False
        for arg in abi.get("inputs", []):
            if arg.get("name") == field_name and arg.get("indexed"):
                return True
        return False

    async def _get_exit_logs(
        self,
        context: StakewiseVaultContext,
        event: ContractEvent,
        filter_field: str,
        filter_value: str,
        from_block: int,
        to_block: int,
    ) -> list[EventData]:
        if self._etherscan_api_url:
            logs = await self._etherscan_fetch_logs(
                event=event,
                contract_address=context.address,
                filter_field=filter_field,
                filter_value=filter_value,
                from_block=from_block,
                to_block=to_block,
            )
            if logs is not None:
                return logs

        try:
            return await self._rpc(
                event.get_logs,
                from_block=from_block,
                to_block=to_block,
                argument_filters={filter_field: filter_value},
            )
        except ValueError as exc:  # pragma: no cover - provider variance
            event_name = getattr(event, "abi", {}).get("name", "unknown")
            logger.warning(
                "StakeWise exit log query failed — event=%s filter=%s value=%s chunk=[%d,%d] err=%s",
                event_name,
                filter_field,
                filter_value,
                from_block,
                to_block,
                exc,
            )
            return []

    async def _etherscan_fetch_logs(
        self,
        *,
        event: ContractEvent,
        contract_address: str,
        filter_field: str,
        filter_value: str,
        from_block: int,
        to_block: int,
    ) -> list[EventData] | None:
        if not self._etherscan_api_url:
            return None

        abi = getattr(event, "abi", None)
        if not abi:
            return None

        topic_values = self._resolve_etherscan_topics(
            event, {filter_field: filter_value}
        )
        if not topic_values or not topic_values[0]:
            return None
        logs: list[EventData] = []
        page = 1
        logger.debug(
            "StakeWise Etherscan log query start — contract=%s event=%s filter=%s value=%s",
            contract_address,
            event.event_name,
            filter_field,
            filter_value,
        )
        while True:
            payload = await asyncio.to_thread(
                self._etherscan_call,
                contract_address,
                topic_values,
                from_block,
                to_block,
                page,
            )
            if payload is None:
                return None

            if payload.get("status") == "1":
                logger.debug(payload.get("result"))

            status = payload.get("status", "").strip()
            message = payload.get("message", "").strip().lower()
            result = payload.get("result")

            if status != "1":
                if isinstance(result, str) and result.lower() == "no records found":
                    break
                if message == "no records found":
                    break
                event_name = getattr(event, "abi", {}).get("name", "unknown")
                logger.warning(
                    "StakeWise Etherscan log query failed — event=%s filter=%s value=%s chunk=[%d,%d] message=%s",
                    event_name,
                    filter_field,
                    filter_value,
                    from_block,
                    to_block,
                    payload.get("message"),
                )
                return None

            if not isinstance(result, list):
                logger.warning(f"Unexpected Etherscan logs result: {result}")
                return None

            for raw_log in result:
                decoded = self._process_etherscan_log(event, raw_log)
                logger.debug(f"Etherscan decoded log: {decoded}")
                if decoded is not None:
                    logs.append(decoded)

            if len(result) < self._etherscan_page_size:
                break
            page += 1

        logger.debug(f"Etherscan log query completed, total logs: {len(logs)}")
        return logs

    @backoff.on_exception(
        backoff.expo,
        (requests.RequestException, ValueError),
        max_time=30,
        jitter=backoff.full_jitter,
    )
    def _etherscan_call(
        self,
        contract_address: str,
        topics: Sequence[str | None],
        from_block: int,
        to_block: int,
        page: int,
    ) -> EtherscanLogsResponse | None:
        if not self._etherscan_api_url:
            return None

        params: dict[str, Any] = {
            "module": "logs",
            "action": "getLogs",
            "address": contract_address,
            "fromBlock": str(from_block),
            "toBlock": str(to_block),
            "page": page,
            "offset": max(1, self._etherscan_page_size),
            "sort": "asc",
        }
        if self._etherscan_chain_id is not None:
            params["chainid"] = str(self._etherscan_chain_id)
        topic0 = topics[0] if len(topics) > 0 else None
        topic1 = topics[1] if len(topics) > 1 else None
        topic2 = topics[2] if len(topics) > 2 else None
        if topic0:
            params["topic0"] = topic0
        if topic1:
            params["topic1"] = topic1
            params["topic0_1_opr"] = "and"
        if topic2:
            params["topic2"] = topic2
            params["topic0_2_opr"] = "and"
        if self._etherscan_api_key:
            params["apikey"] = self._etherscan_api_key

        response = self._etherscan_session.get(
            self._etherscan_api_url,
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Etherscan payload")
        return cast(EtherscanLogsResponse, payload)

    def _resolve_etherscan_topics(
        self,
        event: ContractEvent,
        argument_filters: dict[str, str],
    ) -> list[str | None]:
        try:
            params = event._get_event_filter_params(event.abi, argument_filters)
        except Exception:
            return []

        topics = params.get("topics") or []
        resolved: list[str | None] = []
        for index in range(len(topics)):
            resolved.append(self._extract_topic(topics, index))
        return resolved

    @staticmethod
    def _extract_topic(topics: Sequence[Any], index: int) -> str | None:
        if len(topics) <= index:
            return None

        value = topics[index]
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            if isinstance(value, bytearray):
                value = bytes(value)
            return Web3.to_hex(value)
        if isinstance(value, str):
            return value
        return Web3.to_hex(value)

    def _process_etherscan_log(
        self,
        event: ContractEvent,
        raw_log: EtherscanLogsResult,
    ) -> EventData | None:
        try:
            formatted = self._format_etherscan_log(raw_log)
            # logger.debug(f"Processed log {formatted}")
            return event.process_log(formatted)
        except Exception:
            return None

    @staticmethod
    def _format_etherscan_log(raw_log: EtherscanLogsResult) -> dict[str, Any]:
        def to_int(value: str | None) -> int:
            if not value:
                return 0
            return Web3.to_int(hexstr=HexStr(value))

        data_hex = raw_log.get("data") or "0x"
        block_hash_hex = raw_log.get("blockHash") or "0x0"
        tx_hash_hex = raw_log.get("transactionHash") or "0x0"
        topics_hex = raw_log.get("topics", []) or []

        return {
            "address": raw_log.get("address"),
            "blockHash": block_hash_hex,
            "blockNumber": to_int(raw_log.get("blockNumber")),
            "data": data_hex,
            "logIndex": to_int(raw_log.get("logIndex")),
            "topics": [
                Web3.to_bytes(hexstr=HexStr(topic)) for topic in topics_hex if topic
            ],
            "transactionHash": tx_hash_hex,
            "transactionIndex": to_int(raw_log.get("transactionIndex")),
        }

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
        context: StakewiseVaultContext,
        user_state: AccountState,
        tickets: list[ExitQueueTicket],
    ) -> ExitExposure:
        eth_in_queue = 0
        eth_claimable = 0
        escrow_os_shares = 0

        for ticket in tickets:
            ticket_assets = ticket.assets_hint
            if ticket_assets is None:
                ticket_assets = await self._rpc(
                    context.contract.functions.convertToAssets(ticket.shares).call,
                    block_identifier=self.block_identifier,
                )
                ticket_assets = int(ticket_assets)

            if ticket.receiver == self.os_token_vault_escrow_address:
                escrow_state = await self._fetch_escrow_state(
                    context.address, ticket.ticket
                )
                if escrow_state is None:
                    continue
                os_shares, exited_assets = escrow_state
                escrow_os_shares += os_shares
                eth_claimable += exited_assets
                pending_queue = max(ticket_assets - exited_assets, 0)
                if pending_queue:
                    eth_in_queue += pending_queue
                continue

            exit_queue_index = await self._fetch_exit_queue_index(
                context.contract, ticket.ticket
            )
            if exit_queue_index is None or exit_queue_index < 0:
                eth_in_queue += ticket_assets
                continue

            exited_assets = min(
                ticket_assets,
                await self._calculate_exited_assets(
                    context.contract,
                    ticket.receiver,
                    ticket.ticket,
                    ticket.timestamp,
                    exit_queue_index,
                ),
            )
            eth_claimable += exited_assets
            eth_in_queue += ticket_assets - exited_assets

        os_liabilities = user_state.os_shares + escrow_os_shares
        return ExitExposure(
            staked_eth=user_state.assets,
            eth_in_queue=eth_in_queue,
            eth_claimable=eth_claimable,
            os_shares_liability=os_liabilities,
            escrow_os_shares=escrow_os_shares,
            ticket_count=len(tickets),
        )

    async def _fetch_exit_queue_index(
        self, vault_contract: Contract, ticket: int
    ) -> int | None:
        try:
            index = await self._rpc(
                vault_contract.functions.getExitQueueIndex(ticket).call,
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
        self,
        vault_contract: Contract,
        receiver: str,
        ticket: int,
        timestamp: int,
        exit_queue_index: int,
    ) -> int:
        try:
            _, _, exit_assets = await self._rpc(
                vault_contract.functions.calculateExitedAssets(
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

    async def _fetch_escrow_state(
        self, vault_address: str, ticket: int
    ) -> tuple[int, int] | None:
        try:
            owner, exited_assets, os_token_shares = await self._rpc(
                self.os_token_vault_escrow.functions.getPosition(
                    vault_address, ticket
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

    def _resolve_min_block(self) -> int:
        """Always start from block 0 so every historical event is scanned."""
        return 0

    @staticmethod
    def _append_asset(assets: list[AssetData], address: str, amount: int) -> None:
        if amount:
            assets.append(AssetData(asset_address=address, amount=amount))

    def _log_summary(self, user: str, exposure: ExitExposure) -> None:
        logger.debug(
            "StakeWise summary for %s — eth_collateral=%d (staked=%d, queue=%d, claimable=%d), os_liabilities=%d (escrow_shares=%d) tickets=%d",
            user,
            exposure.eth_collateral,
            exposure.staked_eth,
            exposure.eth_in_queue,
            exposure.eth_claimable,
            exposure.os_shares_liability,
            exposure.escrow_os_shares,
            exposure.ticket_count,
        )
