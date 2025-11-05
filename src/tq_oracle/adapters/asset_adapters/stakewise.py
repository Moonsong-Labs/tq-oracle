from __future__ import annotations

import asyncio
import random
import backoff
from web3 import Web3
from web3.exceptions import ProviderConnectionError

from ...abi import (
    load_stakewise_leverage_strategy_abi,
    load_stakewise_os_token_controller_abi,
    load_stakewise_vault_abi,
)
from ...constants import STAKEWISE_ADDRESSES
from ...logger import get_logger
from ...settings import OracleSettings
from .base import AssetData, BaseAssetAdapter

logger = get_logger(__name__)


class StakeWiseAdapter(BaseAssetAdapter):
    """Adapter for StakeWise vault positions (staking + boost)."""

    def __init__(self, config: OracleSettings, *, vault_address: str | None = None):
        super().__init__(config)

        rpc_url = config.vault_rpc_required
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {rpc_url}")

        stakewise_defaults = STAKEWISE_ADDRESSES.get(config.network.value)
        network_assets = config.assets

        vault_address = (
            vault_address
            or config.stakewise_vault_address
            or (stakewise_defaults.get("vault") if stakewise_defaults else None)
        )

        controller_address = config.stakewise_os_token_vault_controller or (
            stakewise_defaults["controller"] if stakewise_defaults else None
        )
        strategy_address = config.stakewise_leverage_strategy_address or (
            stakewise_defaults["leverage_strategy"] if stakewise_defaults else None
        )
        debt_asset = (
            config.stakewise_debt_asset
            or (stakewise_defaults["debt_asset"] if stakewise_defaults else None)
            or (network_assets.get("WETH") if network_assets else None)
        )
        os_token_address = config.stakewise_os_token_address or (
            stakewise_defaults["os_token"] if stakewise_defaults else None
        )

        missing_fields = []
        if not vault_address:
            missing_fields.append("stakewise_vault_address")
        if not controller_address:
            missing_fields.append("stakewise_os_token_vault_controller")
        if not strategy_address:
            missing_fields.append("stakewise_leverage_strategy_address")
        if not debt_asset:
            missing_fields.append("stakewise_debt_asset")
        if not os_token_address:
            missing_fields.append("stakewise_os_token_address")

        if missing_fields:
            raise ValueError(
                "Missing StakeWise configuration values: "
                f"{', '.join(missing_fields)}. Provide them via configuration or"
                f" ensure defaults exist for network '{config.network.value}'."
            )

        # Narrow Optional types for attributes after validation above.
        assert isinstance(vault_address, str)
        assert isinstance(controller_address, str)
        assert isinstance(strategy_address, str)
        assert isinstance(debt_asset, str)
        assert isinstance(os_token_address, str)

        self.block_identifier = config.block_number_required
        eth_asset = config.assets["ETH"]
        if eth_asset is None:
            raise ValueError("ETH address must be configured for StakeWise adapter")
        self.eth_asset: str = eth_asset

        self.debt_asset: str = debt_asset
        self.os_token_address: str = os_token_address
        self.vault_address = self.w3.to_checksum_address(vault_address)
        self.controller_address = self.w3.to_checksum_address(controller_address)
        self.strategy_address = self.w3.to_checksum_address(strategy_address)

        vault_abi = load_stakewise_vault_abi()
        controller_abi = load_stakewise_os_token_controller_abi()
        strategy_abi = load_stakewise_leverage_strategy_abi()

        self.vault = self.w3.eth.contract(address=self.vault_address, abi=vault_abi)
        self.controller = self.w3.eth.contract(
            address=self.controller_address, abi=controller_abi
        )
        self.strategy = self.w3.eth.contract(
            address=self.strategy_address, abi=strategy_abi
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

        user_shares = await self._vault_shares(user)
        user_assets = await self._vault_assets(user_shares)
        user_os_token_shares = await self._os_token_shares(user)
        user_os_token_assets = await self._os_token_assets(user_os_token_shares)

        proxy_address = await self._rpc(
            self.strategy.functions.getStrategyProxy(self.vault_address, user).call,
            block_identifier=self.block_identifier,
        )

        proxy_assets = 0
        proxy_os_token_assets = 0
        borrowed_assets = 0
        supplied_os_token_assets = 0

        if proxy_address and int(proxy_address, 16) != 0:
            proxy = self.w3.to_checksum_address(proxy_address)
            proxy_shares = await self._vault_shares(proxy)
            proxy_assets = await self._vault_assets(proxy_shares)

            proxy_os_token_shares = await self._os_token_shares(proxy)
            proxy_os_token_assets = await self._os_token_assets(proxy_os_token_shares)

            borrowed_assets, supplied_os_token_shares = await self._rpc(
                self.strategy.functions.getBorrowState(proxy).call,
                block_identifier=self.block_identifier,
            )
            supplied_os_token_assets = await self._os_token_assets(
                supplied_os_token_shares
            )

        total_eth = user_assets + proxy_assets
        total_os_token = user_os_token_assets + proxy_os_token_assets

        assets: list[AssetData] = []
        if total_eth:
            assets.append(
                AssetData(asset_address=self.eth_asset, amount=int(total_eth))
            )
        if total_os_token:
            assets.append(
                AssetData(
                    asset_address=self.os_token_address, amount=int(total_os_token)
                )
            )
        if borrowed_assets:
            assets.append(
                AssetData(asset_address=self.debt_asset, amount=int(borrowed_assets))
            )
        logger.debug(
            "StakeWise summary for %s — eth=%d, osToken=%d, borrowed=%d, supplied_osToken=%d",
            user,
            total_eth,
            total_os_token,
            borrowed_assets,
            supplied_os_token_assets,
        )

        return assets
