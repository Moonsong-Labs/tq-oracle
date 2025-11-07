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
    load_stakewise_vault_abi,
)
from ...constants import STAKEWISE_ADDRESSES
from ...logger import get_logger
from ...settings import OracleSettings
from .base import AssetData, BaseAssetAdapter

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StakeWiseAddressesResolved:
    vault: str
    controller: str
    strategy: str
    debt_asset: str
    os_token: str


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
    supplied_os_token_assets: int = 0
    minted_os_token_shares: int = 0
    minted_os_token_assets: int = 0
    exit_assets: int = 0
    exit_os_token_shares: int = 0
    exit_os_token_assets: int = 0


class StakeWiseAdapter(BaseAssetAdapter):
    """Adapter for StakeWise vault positions (staking + boost)."""

    def __init__(self, config: OracleSettings, *, vault_address: str | None = None):
        super().__init__(config)

        self.w3 = self._build_web3(config.vault_rpc_required)

        resolved = self._resolve_addresses(config, vault_address)

        self.block_identifier = config.block_number_required
        self.eth_asset = self._resolve_eth_asset(config)
        self.debt_asset = resolved.debt_asset
        self.os_token_address = resolved.os_token

        self.vault_address = self.w3.to_checksum_address(resolved.vault)
        self.controller_address = self.w3.to_checksum_address(resolved.controller)
        self.strategy_address = self.w3.to_checksum_address(resolved.strategy)

        self.vault = self._build_contract(self.vault_address, load_stakewise_vault_abi())
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

    async def _vault_shares(self, account: str) -> int:
        return await self._rpc(
            self.vault.functions.getShares(account).call,
            block_identifier=self.block_identifier,
        )

    async def _vault_assets(self, shares: int) -> int:
        if shares == 0:
            return 0
        return await self._rpc(
            self.vault.functions.convertToAssets(shares).call,
            block_identifier=self.block_identifier,
        )

    async def _os_token_shares(self, account: str) -> int:
        return await self._rpc(
            self.vault.functions.osTokenPositions(account).call,
            block_identifier=self.block_identifier,
        )

    async def _os_token_assets(self, shares: int) -> int:
        if shares == 0:
            return 0
        return await self._rpc(
            self.controller.functions.convertToAssets(shares).call,
            block_identifier=self.block_identifier,
        )

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
            debt_asset=cast(str, values["stakewise_debt_asset"]),
            os_token=cast(str, values["stakewise_os_token_address"]),
        )

    def _build_contract(self, address: str, abi: Iterable[dict]) -> Contract:
        checksum = self.w3.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum, abi=list(abi))

    async def _fetch_account_state(self, account: str) -> AccountState:
        shares, os_shares = await asyncio.gather(
            self._vault_shares(account),
            self._os_token_shares(account),
        )
        assets = await self._vault_assets(shares)
        return AccountState(
            assets=assets,
            os_shares=os_shares,
        )

    async def _fetch_proxy_state(self, user: str) -> ProxyState:
        proxy_address = await self._rpc(
            self.strategy.functions.getStrategyProxy(self.vault_address, user).call,
            block_identifier=self.block_identifier,
        )

        if not proxy_address or int(proxy_address, 16) == 0:
            logger.info("StakeWise proxy missing — user=%s, treating as direct stake", user)
            return ProxyState()

        proxy = self.w3.to_checksum_address(proxy_address)
        logger.debug("StakeWise proxy resolved — user=%s proxy=%s", user, proxy)
        (
            (staked_assets, minted_os_token_shares, minted_os_token_assets),
            (borrowed_assets, supplied_os_token_shares, supplied_os_token_assets),
            (exit_assets, exit_os_token_shares, exit_os_token_assets),
        ) = await asyncio.gather(
            self._get_proxy_vault_state(proxy),
            self._get_borrow_state(proxy),
            self._get_exit_state(proxy),
        )
        return ProxyState(
            address=proxy,
            staked_assets=staked_assets,
            borrowed_assets=borrowed_assets,
            supplied_os_token_shares=supplied_os_token_shares,
            supplied_os_token_assets=supplied_os_token_assets,
            minted_os_token_shares=minted_os_token_shares,
            minted_os_token_assets=minted_os_token_assets,
            exit_assets=exit_assets,
            exit_os_token_shares=exit_os_token_shares,
            exit_os_token_assets=exit_os_token_assets,
        )

    async def _get_borrow_state(self, proxy: str) -> tuple[int, int, int]:
        try:
            borrowed_assets, supplied_os_token_shares = await self._rpc(
                self.strategy.functions.getBorrowState(proxy).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            return 0, 0, 0
        supplied_os_token_assets = await self._os_token_assets(supplied_os_token_shares)
        return borrowed_assets, supplied_os_token_shares, supplied_os_token_assets

    async def _get_proxy_vault_state(
        self, proxy: str
    ) -> tuple[int, int, int]:
        get_vault_state_fn = getattr(self.strategy.functions, "getVaultState", None)
        if get_vault_state_fn is None:
            account_state = await self._fetch_account_state(proxy)
            logger.debug(
                "StakeWise using vault fallback for proxy=%s (strategy getter unavailable)",
                proxy,
            )
            minted_os_token_assets = await self._os_token_assets(account_state.os_shares)
            return account_state.assets, account_state.os_shares, minted_os_token_assets
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
            minted_os_token_assets = await self._os_token_assets(account_state.os_shares)
            return account_state.assets, account_state.os_shares, minted_os_token_assets

        minted_os_token_assets = await self._os_token_assets(minted_os_token_shares)
        return (
            int(staked_assets),
            int(minted_os_token_shares),
            int(minted_os_token_assets),
        )

    async def _get_exit_state(
        self, proxy: str
    ) -> tuple[int, int, int]:
        is_exiting_fn = getattr(
            self.strategy.functions, "isStrategyProxyExiting", None
        )
        get_exit_state_fn = getattr(self.strategy.functions, "getProxyExitState", None)

        if is_exiting_fn is None or get_exit_state_fn is None:
            return 0, 0, 0

        try:
            is_exiting = await self._rpc(
                is_exiting_fn(proxy).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            return 0, 0, 0

        if not is_exiting:
            return 0, 0, 0

        try:
            exit_assets, exit_os_token_shares = await self._rpc(
                get_exit_state_fn(proxy).call,
                block_identifier=self.block_identifier,
            )
        except (ContractLogicError, ValueError):  # pragma: no cover - defensive
            return 0, 0, 0

        exit_os_token_assets = await self._os_token_assets(exit_os_token_shares)
        logger.info(
            "StakeWise proxy exiting — proxy=%s exit_eth=%d exit_osETH_shares=%d",
            proxy,
            exit_assets,
            exit_os_token_shares,
        )
        return (
            int(exit_assets),
            int(exit_os_token_shares),
            int(exit_os_token_assets),
        )

    async def _build_positions(
        self, user_state: AccountState, proxy_state: ProxyState
    ) -> tuple[list[AssetData], dict[str, int]]:
        staked_eth = user_state.assets + proxy_state.staked_assets
        exit_eth = proxy_state.exit_assets
        collateral_eth = staked_eth + exit_eth
        borrowed_eth = proxy_state.borrowed_assets

        minted_os_token_shares = (
            user_state.os_shares + proxy_state.minted_os_token_shares
        )
        os_token_liabilities = minted_os_token_shares
        os_token_assets = (
            proxy_state.supplied_os_token_assets + proxy_state.exit_os_token_assets
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
            "supplied_os_assets": proxy_state.supplied_os_token_assets,
            "exit_os_assets": proxy_state.exit_os_token_assets,
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
            " osToken_assets=%d (supplied=%d, exit=%d) vs liabilities=%d (shares=%d),"
            " proxy_liability_delta=%d",
            user,
            summary["net_eth"],
            summary["staked_eth"],
            summary["exit_eth"],
            summary["borrowed_eth"],
            summary["os_assets"],
            summary["supplied_os_assets"],
            summary["exit_os_assets"],
            summary["os_liabilities"],
            summary["minted_os_shares"],
            summary["proxy_gap"],
        )
