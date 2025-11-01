from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from web3 import Web3
from web3.eth import Contract
from web3.constants import ADDRESS_ZERO
import backoff
import random
from web3.exceptions import ProviderConnectionError
from ...logger import get_logger
from ...abi import (
    load_multicall_abi,
    load_vault_abi,
    load_compact_collector_abi,
    load_compact_collector_bytecode,
)
from .base import AssetData, BaseAssetAdapter, AdapterChain
from eth_abi.abi import decode

if TYPE_CHECKING:
    from ...settings import OracleSettings

logger = get_logger(__name__)


class StrETHAdapter(BaseAssetAdapter):
    streth_address: str
    multicall: Contract
    chain: AdapterChain
    w3: Web3

    def __init__(self, config: OracleSettings, chain: str = "vault_chain"):
        """Initialize the adapter.

        Args:
            config: Oracle configuration
            chain: Which chain to query - always "vault_chain"
        """
        super().__init__(config, chain=chain)

        self.w3 = Web3(Web3.HTTPProvider(config.vault_rpc))
        self.block_number = config.block_number_required

        self.vault_address = Web3.to_checksum_address(config.vault_address)
        self.streth_address = Web3.to_checksum_address(config.streth)
        self.multicall: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.multicall), abi=load_multicall_abi()
        )

        self._rpc_sem = asyncio.Semaphore(getattr(self.config, "max_calls", 5))
        self._rpc_delay = getattr(self.config, "rpc_delay", 0.15)  # seconds
        self._rpc_jitter = getattr(self.config, "rpc_jitter", 0.10)  # seconds

    @backoff.on_exception(
        backoff.expo, (ProviderConnectionError), max_time=30, jitter=backoff.full_jitter
    )
    async def _rpc(self, fn, *args, **kwargs):
        """Throttle + backoff a single RPC."""
        async with self._rpc_sem:
            try:
                return await asyncio.to_thread(fn, *args, **kwargs)
            finally:
                delay = self._rpc_delay + random.random() * self._rpc_jitter
                if delay > 0:
                    await asyncio.sleep(delay)

    @property
    def adapter_name(self) -> str:
        return "streth"

    @property
    def chain(self) -> AdapterChain:
        return AdapterChain.VAULT_CHAIN

    async def _fetch_assets(self, subvault_addresses: list[str]) -> list[AssetData]:
        """Fetch strETH positions for the given subvaults on the configured chain.

        Args:
            subvault_addresses: List of subvaults to query

        Returns:
            List of AssetData objects containing asset addresses and balances
        """
        compact_collector_abi = load_compact_collector_abi()
        compact_collector: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(ADDRESS_ZERO),
            abi=compact_collector_abi,
        )

        compact_collector_bytecode = load_compact_collector_bytecode()
        runtime_bytecode: bytes = await self._rpc(
            self.w3.eth.call,
            transaction={"data": compact_collector_bytecode},
            block_identifier=self.block_number,
        )

        address = Web3.to_checksum_address("0x" + "dead0dead".zfill(40))

        calls = []
        for subvault in subvault_addresses:
            calls.append(
                [
                    address,
                    compact_collector.encode_abi(
                        "getPosition",
                        args=[
                            self.streth_address,
                            ADDRESS_ZERO,
                            Web3.to_checksum_address(subvault),
                        ],
                    ),
                ]
            )

        call_results = (
            await self._rpc(
                self.multicall.functions.aggregate(calls).call,
                block_identifier=self.block_number,
                state_override={address: {"code": runtime_bytecode}},
            )
        )[1]

        cumulative_amounts: dict[str, int] = {}

        for call_result in call_results:
            assets, amounts = decode(["address[]", "uint256[]"], call_result)
            for asset, amount in zip(assets, amounts):
                if amount != 0:
                    cumulative_amounts[asset] = (
                        cumulative_amounts.get(asset, 0) + amount
                    )

        result: list[AssetData] = []
        for asset, amount in cumulative_amounts.items():
            result.append(AssetData(Web3.to_checksum_address(asset), amount))
        return result

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        return await self._fetch_assets([subvault_address])

    async def fetch_all_assets(self) -> list[AssetData]:
        """Fetch strETH positions for all subvaults of the vault on the configured chain.

        Returns:
            List of AssetData objects containing asset addresses and balances
        """
        vault_contract: Contract = self.w3.eth.contract(
            address=self.vault_address, abi=load_vault_abi()
        )
        count: int = await self._rpc(
            vault_contract.functions.subvaults().call,
            block_identifier=self.block_number,
        )

        calls = [
            [
                vault_contract.address,
                vault_contract.encode_abi("subvaultAt", args=[index]),
            ]
            for index in range(count)
        ]
        responses = (
            await self._rpc(
                self.multicall.functions.aggregate(calls).call,
                block_identifier=self.block_number,
            )
        )[1]
        subvaults = [decode(["address"], response)[0] for response in responses]
        return await self._fetch_assets(subvaults)
