from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from web3 import Web3
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
    streth_price_feed_address: str
    multicall: str
    chain: AdapterChain

    def __init__(self, config: OracleSettings, chain: str = "vault_chain"):
        """Initialize the adapter."""
        super().__init__(config, chain=chain)

        self.w3 = Web3(Web3.HTTPProvider(config.vault_rpc))

        self.streth_address = config.streth
        self.multi_call = self.w3.eth.contract(
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
        compact_collector_abi = load_compact_collector_abi()
        compact_collector = self.w3.eth.contract(
            address=Web3.to_checksum_address("0x" + "".zfill(40)),
            abi=compact_collector_abi,
        )

        compact_collector_bytecode = load_compact_collector_bytecode()
        runtime_bytecode = self.w3.eth.call(
            transaction={"to": "", "data": bytes(compact_collector_bytecode)}
        )

        address = Web3.to_checksum_address("0x" + "dead0dead".zfill(40))

        calldata = compact_collector.encode_abi(
            "getPosition",
            args=[
                Web3.to_checksum_address(self.streth_address),
                "0x" + "".zfill(40),
                Web3.to_checksum_address(subvault_addresses[0]),
            ],
        )

        call_results = self.w3.eth.call(
            {"to": address, "data": calldata},
            "latest",
            state_override={address: {"code": runtime_bytecode}},
        )

        assets, amounts = decode(["address[]", "uint256[]"], call_results)

        result: list[AssetData] = []
        for asset, amount in zip(list(assets), list(amounts)):
            if amount != 0:
                result.append(AssetData(Web3.to_checksum_address(asset), amount))
        return result

    async def fetch_assets(self, subvault_address: str) -> list[AssetData]:
        return await self._fetch_assets([subvault_address])

    async def fetch_all_assets(self) -> list[AssetData]:
        streth_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.streth_address), abi=load_vault_abi()
        )
        count: int = await self._rpc(streth_contract.functions.subvaults().call)

        calls = [
            [
                streth_contract.address,
                streth_contract.encode_abi("subvaultAt", args=[index]),
            ]
            for index in range(count)
        ]
        responses = (await self._rpc(self.multi_call.functions.aggregate(calls).call))[
            1
        ]
        subvaults = [decode(["address"], response)[0] for response in responses]
        return await self._fetch_assets(subvaults)
