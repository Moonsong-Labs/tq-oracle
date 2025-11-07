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
    load_erc20_abi,
    load_stakewise_leverage_strategy_abi,
    load_stakewise_os_token_controller_abi,
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
    controller: str
    strategy: str
    os_token_vault_escrow: str
    debt_asset: str
    os_token: str


@dataclass(frozen=True, slots=True)
class ExitQueuePosition:
    ticket: int
    timestamp: int
    block_number: int
    shares: int


@dataclass(frozen=True, slots=True)
class ExitExposure:
    eth: int = 0
    os_token_shares: int = 0
    position: ExitQueuePosition | None = None


@dataclass(frozen=True, slots=True)
class AccountState:
    assets: int = 0
    os_shares: int = 0


@dataclass(frozen=True, slots=True)
class ProxyState:
    address: Optional[str] = None
    staked_assets: int = 0
    borrowed_assets: int = 0
    supplied_os_token_shares: int = 0
    minted_os_token_shares: int = 0
    exit_eth: int = 0
    exit_os_token_shares: int = 0
    loose_os_token_shares: int = 0
    exit_ticket: ExitQueuePosition | None = None


class StakeWiseAdapter(BaseAssetAdapter):
    """Adapter for StakeWise vault positions (staking + boost)."""

    def __init__(
        self,
        config: OracleSettings,
        *,
        vault_address: str | None = None,
        strategy_deploy_block: int | None = None,
    ):
        super().__init__(config)

        self.w3 = self._build_web3(config.vault_rpc_required)

        resolved = self._resolve_addresses(config, vault_address)

        self.block_identifier = config.block_number_required
        self.eth_asset = self._resolve_eth_asset(config)
        self.debt_asset = resolved.debt_asset
        self.os_token_address = resolved.os_token
        self.os_token_vault_escrow_address = self.w3.to_checksum_address(
            resolved.os_token_vault_escrow
        )

        self.vault_address = self.w3.to_checksum_address(resolved.vault)
        self.controller_address = self.w3.to_checksum_address(resolved.controller)
        self.strategy_address = self.w3.to_checksum_address(resolved.strategy)

        self.vault = self._build_contract(
            self.vault_address, load_stakewise_vault_abi()
        )
        self.controller = self._build_contract(
            self.controller_address,
            load_stakewise_os_token_controller_abi(),
        )
        self.strategy = self._build_contract(
            self.strategy_address,
            load_stakewise_leverage_strategy_abi(),
        )
        self.os_token_contract: Contract = self._build_contract(
            self.os_token_address, load_erc20_abi()
        )
        self.os_token_vault_escrow: Contract = self._build_contract(
            self.os_token_vault_escrow_address,
            load_stakewise_os_token_vault_escrow_abi(),
        )

        self._is_strategy_proxy_exiting_fn = getattr(
            self.strategy.functions, "isStrategyProxyExiting", None
        )
        self._exit_event_topic = self.w3.keccak(
            text="ExitQueueEntered(address,address,uint256,uint256,uint256,uint256)"
        )
        self._vault_topic = self._address_topic(self.vault_address)
        self._exit_log_chunk = 200
        self._strategy_deploy_block = (
            strategy_deploy_block
            or config.stakewise_leverage_strategy_deploy_block
            or 0
        )
        self._exit_position_cache: dict[str, ExitQueuePosition] = {}

        self._rpc_sem = asyncio.Semaphore(getattr(config, "max_calls", 5))
        self._rpc_delay = getattr(config, "rpc_delay", 0.15)
        self._rpc_jitter = getattr(config, "rpc_jitter", 0.10)

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

        user_state, proxy_state = await asyncio.gather(
            self._fetch_account_state(user),
            self._fetch_proxy_state(user),
        )

        assets, summary = await self._build_positions(user_state, proxy_state)
        self._log_summary(user, summary)
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
        network_assets = config.assets

        values = {
            "stakewise_vault_address": override_vault
            or config.stakewise_vault_address
            or defaults.get("vault"),
            "stakewise_os_token_vault_controller": config.stakewise_os_token_vault_controller
            or defaults.get("controller"),
            "stakewise_leverage_strategy_address": config.stakewise_leverage_strategy_address
            or defaults.get("leverage_strategy"),
            "stakewise_os_token_vault_escrow": config.stakewise_os_token_vault_escrow
            or defaults.get("os_token_vault_escrow"),
            "stakewise_debt_asset": config.stakewise_debt_asset
            or defaults.get("debt_asset")
            or network_assets.get("WETH"),
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
            controller=cast(str, values["stakewise_os_token_vault_controller"]),
            strategy=cast(str, values["stakewise_leverage_strategy_address"]),
            os_token_vault_escrow=cast(str, values["stakewise_os_token_vault_escrow"]),
            debt_asset=cast(str, values["stakewise_debt_asset"]),
            os_token=cast(str, values["stakewise_os_token_address"]),
        )

    def _build_contract(self, address: str, abi: Iterable[dict]) -> Contract:
        checksum = self.w3.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum, abi=list(abi))

    @staticmethod
    def _address_topic(address: str) -> str:
        return "0x" + address.lower().removeprefix("0x").zfill(64)

    async def _fetch_latest_exit_position(self, user: str) -> ExitQueuePosition | None:
        cached = self._exit_position_cache.get(user)
        if cached:
            return cached

        user_topic = self._address_topic(user)
        to_block = self.block_identifier
        min_block = self._strategy_deploy_block

        while to_block >= min_block:
            from_block = max(min_block, to_block - self._exit_log_chunk + 1)
            logger.debug(
                "StakeWise exit log scan — user=%s chunk=[%d,%d]",
                user,
                from_block,
                to_block,
            )
            params = {
                "address": self.strategy_address,
                "fromBlock": from_block,
                "toBlock": to_block,
                "topics": [
                    self._exit_event_topic,
                    self._vault_topic,
                    user_topic,
                ],
            }
            try:
                logs = await self._rpc(self.w3.eth.get_logs, params)
            except ValueError as exc:  # pragma: no cover - provider variance
                logger.warning(
                    "StakeWise exit log query failed — user=%s chunk=[%d,%d] err=%s",
                    user,
                    from_block,
                    to_block,
                    exc,
                )
                to_block = from_block - 1
                continue

            if logs:
                latest = max(
                    logs,
                    key=lambda entry: (entry["blockNumber"], entry["logIndex"]),
                )
                processed = self.strategy.events.ExitQueueEntered().process_log(latest)
                args = processed["args"]
                position = ExitQueuePosition(
                    ticket=int(args["positionTicket"]),
                    timestamp=int(args["timestamp"]),
                    block_number=int(latest["blockNumber"]),
                    shares=int(args["osTokenShares"]),
                )
                self._exit_position_cache[user] = position
                logger.info(
                    "StakeWise exit ticket found — user=%s ticket=%d shares=%d block=%d",
                    user,
                    position.ticket,
                    position.shares,
                    position.block_number,
                )
                return position

            to_block = from_block - 1

        logger.warning(
            "StakeWise exit ticket missing after log scan — user=%s min_block=%d",
            user,
            min_block,
        )
        return None

    async def _os_token_balance(self, account: str) -> int:
        return await self._rpc(
            self.os_token_contract.functions.balanceOf(account).call,
            block_identifier=self.block_identifier,
        )

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
        return AccountState(assets=assets, os_shares=os_shares)

    async def _fetch_proxy_state(self, user: str) -> ProxyState:
        proxy_address = await self._rpc(
            self.strategy.functions.getStrategyProxy(self.vault_address, user).call,
            block_identifier=self.block_identifier,
        )

        if not proxy_address or int(proxy_address, 16) == 0:
            logger.info(
                "StakeWise proxy missing — user=%s, treating as direct stake", user
            )
            return ProxyState()

        proxy = self.w3.to_checksum_address(proxy_address)
        logger.debug("StakeWise proxy resolved — user=%s proxy=%s", user, proxy)
        (
            (staked_assets, minted_os_token_shares),
            (borrowed_assets, supplied_os_token_shares),
            exit_exposure,
            loose_os_token_shares,
        ) = await asyncio.gather(
            self._get_proxy_vault_state(proxy),
            self._get_borrow_state(proxy),
            self._get_exit_exposure(user, proxy),
            self._os_token_balance(proxy),
        )
        return ProxyState(
            address=proxy,
            staked_assets=staked_assets,
            borrowed_assets=borrowed_assets,
            supplied_os_token_shares=supplied_os_token_shares,
            minted_os_token_shares=minted_os_token_shares,
            exit_eth=exit_exposure.eth,
            exit_os_token_shares=exit_exposure.os_token_shares,
            loose_os_token_shares=int(loose_os_token_shares),
            exit_ticket=exit_exposure.position,
        )

    async def _get_borrow_state(self, proxy: str) -> tuple[int, int]:
        try:
            borrowed_assets, supplied_os_token_shares = await self._rpc(
                self.strategy.functions.getBorrowState(proxy).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            return 0, 0
        return borrowed_assets, supplied_os_token_shares

    async def _get_proxy_vault_state(self, proxy: str) -> tuple[int, int]:
        get_vault_state_fn = getattr(self.strategy.functions, "getVaultState", None)
        if get_vault_state_fn is None:
            account_state = await self._fetch_account_state(proxy)
            logger.debug(
                "StakeWise using vault fallback for proxy=%s (strategy getter unavailable)",
                proxy,
            )
            return account_state.assets, account_state.os_shares
        try:
            staked_assets, minted_os_token_shares = await self._rpc(
                get_vault_state_fn(self.vault_address, proxy).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            account_state = await self._fetch_account_state(proxy)
            logger.info(
                "StakeWise getVaultState revert — proxy=%s, falling back to vault shares",
                proxy,
            )
            return account_state.assets, account_state.os_shares

        return int(staked_assets), int(minted_os_token_shares)

    async def _get_exit_exposure(self, user: str, proxy: str) -> ExitExposure:
        if not await self._is_proxy_exiting(proxy):
            return ExitExposure()

        position = await self._fetch_latest_exit_position(user)
        if position is None:
            return ExitExposure()

        exit_queue_index = await self._fetch_exit_queue_index(position.ticket)
        exit_eth = 0
        if exit_queue_index is not None and exit_queue_index >= 0:
            exit_eth = await self._calculate_exited_assets(
                proxy, position, exit_queue_index
            )

        escrow_state = await self._fetch_escrow_state(proxy, position.ticket)
        if escrow_state is None:
            return ExitExposure()
        exit_os_token_shares, exited_assets_ready = escrow_state

        logger.info(
            "StakeWise exit exposure — user=%s proxy=%s ticket=%d shares=%d exit_eth=%d ready_eth=%d",
            user,
            proxy,
            position.ticket,
            exit_os_token_shares,
            exit_eth,
            exited_assets_ready,
        )

        return ExitExposure(
            eth=exit_eth,
            os_token_shares=exit_os_token_shares,
            position=position,
        )

    async def _is_proxy_exiting(self, proxy: str) -> bool:
        if self._is_strategy_proxy_exiting_fn is None:
            return False
        try:
            result = await self._rpc(
                self._is_strategy_proxy_exiting_fn(proxy).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            return False
        return bool(result)

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
        self, proxy: str, position: ExitQueuePosition, exit_queue_index: int
    ) -> int:
        try:
            _, _, exit_assets = await self._rpc(
                self.vault.functions.calculateExitedAssets(
                    proxy,
                    position.ticket,
                    position.timestamp,
                    exit_queue_index,
                ).call,
                block_identifier=self.block_identifier,
            )
            return int(exit_assets)
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            logger.debug(
                "StakeWise calculateExitedAssets failed — proxy=%s ticket=%d index=%d",
                proxy,
                position.ticket,
                exit_queue_index,
            )
            return 0

    async def _fetch_escrow_state(
        self, proxy: str, ticket: int
    ) -> tuple[int, int] | None:
        try:
            owner, exited_assets, os_token_shares = await self._rpc(
                self.os_token_vault_escrow.functions.getPosition(
                    self.vault_address, ticket
                ).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            logger.warning(
                "StakeWise exit escrow lookup failed — proxy=%s ticket=%d",
                proxy,
                ticket,
            )
            return None

        if owner and owner != ZERO_ADDRESS:
            try:
                resolved_owner = self.w3.to_checksum_address(owner)
            except ValueError:  # pragma: no cover - corrupted response
                resolved_owner = owner
            if resolved_owner != proxy:
                logger.warning(
                    "StakeWise exit ticket owner mismatch — proxy=%s owner=%s ticket=%d",
                    proxy,
                    resolved_owner,
                    ticket,
                )
                return None

        return int(os_token_shares), int(exited_assets)

    async def _build_positions(
        self, user_state: AccountState, proxy_state: ProxyState
    ) -> tuple[list[AssetData], dict[str, int]]:
        staked_eth = user_state.assets + proxy_state.staked_assets
        exit_eth = proxy_state.exit_eth
        collateral_eth = staked_eth + exit_eth
        borrowed_eth = proxy_state.borrowed_assets

        minted_os_token_shares = (
            user_state.os_shares + proxy_state.minted_os_token_shares
        )
        os_token_liabilities = minted_os_token_shares + proxy_state.exit_os_token_shares
        os_token_assets = (
            proxy_state.supplied_os_token_shares
            + proxy_state.exit_os_token_shares
            + proxy_state.loose_os_token_shares
        )

        assets: list[AssetData] = []
        self._append_asset(assets, self.eth_asset, collateral_eth)
        self._append_asset(assets, self.eth_asset, -borrowed_eth)
        self._append_asset(assets, self.os_token_address, os_token_assets)
        self._append_asset(assets, self.os_token_address, -os_token_liabilities)

        summary = {
            "net_eth": collateral_eth - borrowed_eth,
            "staked_eth": staked_eth,
            "exit_eth": exit_eth,
            "borrowed_eth": borrowed_eth,
            "os_assets": os_token_assets,
            "supplied_os_shares": proxy_state.supplied_os_token_shares,
            "exit_os_shares": proxy_state.exit_os_token_shares,
            "loose_os_shares": proxy_state.loose_os_token_shares,
            "os_liabilities": os_token_liabilities,
            "minted_os_shares": minted_os_token_shares,
            "proxy_gap": proxy_state.minted_os_token_shares
            - proxy_state.supplied_os_token_shares
            - proxy_state.exit_os_token_shares,
        }
        return assets, summary

    @staticmethod
    def _append_asset(assets: list[AssetData], address: str, amount: int) -> None:
        if amount:
            assets.append(AssetData(asset_address=address, amount=amount))

    def _log_summary(self, user: str, summary: dict[str, int]) -> None:
        logger.debug(
            "StakeWise summary for %s — net_eth=%d (staked=%d, exit=%d, borrowed=%d),"
            " osToken_shares=%d (supplied=%d, exit=%d, loose=%d) vs liabilities=%d (minted=%d, exit=%d),"
            " proxy_liability_delta=%d",
            user,
            summary["net_eth"],
            summary["staked_eth"],
            summary["exit_eth"],
            summary["borrowed_eth"],
            summary["os_assets"],
            summary["supplied_os_shares"],
            summary["exit_os_shares"],
            summary["loose_os_shares"],
            summary["os_liabilities"],
            summary["minted_os_shares"],
            summary["exit_os_shares"],
            summary["proxy_gap"],
        )
