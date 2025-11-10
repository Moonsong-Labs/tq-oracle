from types import SimpleNamespace
from typing import cast

import pytest

from web3.contract import Contract

from tq_oracle.adapters.asset_adapters.stakewise import (
    ExitQueueTicket,
    StakeWiseAdapter,
    StakewiseVaultContext,
)
from tq_oracle.settings import OracleSettings


class _Call:
    def __init__(self, result):
        self._result = result

    def call(self, *args, **kwargs):  # pragma: no cover - helper
        return self._result


class DummyEvent:
    def get_logs(self, *args, **kwargs):  # pragma: no cover - helper
        return []


class DummyEvents:
    def ExitQueueEntered(self):  # pragma: no cover - helper
        return DummyEvent()

    def V2ExitQueueEntered(self):  # pragma: no cover - helper
        return DummyEvent()


class DummyEth:
    def __init__(self):
        self._contract = SimpleNamespace(
            functions=SimpleNamespace(),
            events=DummyEvents(),
        )

    def contract(self, *args, **kwargs):  # pragma: no cover - helper
        return SimpleNamespace(functions=SimpleNamespace(), events=DummyEvents())

    def get_block(self, _block_number):  # pragma: no cover - helper
        return {"timestamp": 0}


class DummyWeb3:
    HTTPProvider = staticmethod(lambda *_args, **_kwargs: None)

    def __init__(self, _provider):
        self.eth = DummyEth()

    def is_connected(self) -> bool:  # pragma: no cover - trivial
        return True

    @staticmethod
    def to_checksum_address(value: str) -> str:  # pragma: no cover - trivial
        return value


@pytest.fixture()
def dummy_web3(monkeypatch):
    monkeypatch.setattr(
        "tq_oracle.adapters.asset_adapters.stakewise.Web3",
        DummyWeb3,
    )


def _build_adapter(dummy_web3) -> StakeWiseAdapter:
    config = OracleSettings(
        vault_rpc="http://localhost",
        block_number=1,
        vault_address="0x0000000000000000000000000000000000000001",
        stakewise_vault_address="0x0000000000000000000000000000000000000002",
        stakewise_os_token_vault_escrow="0x0000000000000000000000000000000000000003",
        stakewise_os_token_address="0x0000000000000000000000000000000000000004",
    )
    return StakeWiseAdapter(config)


@pytest.mark.asyncio
async def test_stakewise_adapter_no_exit_queue(dummy_web3):
    adapter = _build_adapter(dummy_web3)

    async def no_tickets(_self, _context, _user):
        return []

    adapter._scan_exit_queue_tickets = no_tickets.__get__(adapter, StakeWiseAdapter)

    async def direct_rpc(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    adapter._rpc = direct_rpc.__get__(adapter, StakeWiseAdapter)

    shares_map = {"0xuser": 10}
    os_token_shares_map = {"0xuser": 4}

    dummy_contract = cast(
        Contract,
        SimpleNamespace(
            functions=SimpleNamespace(
                getShares=lambda account: _Call(shares_map.get(account, 0)),
                convertToAssets=lambda shares: _Call(shares * 2),
                osTokenPositions=lambda account: _Call(
                    os_token_shares_map.get(account, 0)
                ),
            ),
            events=DummyEvents(),
        ),
    )
    adapter.vault_contexts = [
        StakewiseVaultContext(address="0xvault", contract=dummy_contract, exit_events=[])
    ]
    adapter.vault_address = "0xvault"

    assets = await adapter.fetch_assets("0xuser")

    assert any(
        asset.asset_address == adapter.eth_asset and asset.amount == 20
        for asset in assets
    )
    assert any(
        asset.asset_address == adapter.os_token_address and asset.amount == -4
        for asset in assets
    )


@pytest.mark.asyncio
async def test_stakewise_adapter_exit_queue_direct_receiver(dummy_web3):
    adapter = _build_adapter(dummy_web3)

    async def tickets(_self, _context, _user):
        return [
            ExitQueueTicket(
                ticket=1,
                shares=5,
                receiver="0xuser",
                block_number=10,
                log_index=1,
                timestamp=123,
            )
        ]

    adapter._scan_exit_queue_tickets = tickets.__get__(adapter, StakeWiseAdapter)

    async def direct_rpc(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    adapter._rpc = direct_rpc.__get__(adapter, StakeWiseAdapter)

    async def fake_index(self, _contract, ticket):
        return 7

    adapter._fetch_exit_queue_index = fake_index.__get__(adapter, StakeWiseAdapter)

    async def fake_exited(self, _contract, receiver, ticket, timestamp, index):
        return 4

    adapter._calculate_exited_assets = fake_exited.__get__(adapter, StakeWiseAdapter)

    shares_map = {"0xuser": 10}
    os_token_shares_map = {"0xuser": 4}

    dummy_contract = cast(
        Contract,
        SimpleNamespace(
            functions=SimpleNamespace(
                getShares=lambda account: _Call(shares_map.get(account, 0)),
                convertToAssets=lambda shares: _Call(shares * 2),
                osTokenPositions=lambda account: _Call(
                    os_token_shares_map.get(account, 0)
                ),
            ),
            events=DummyEvents(),
        ),
    )
    adapter.vault_contexts = [
        StakewiseVaultContext(address="0xvault", contract=dummy_contract, exit_events=[])
    ]
    adapter.vault_address = "0xvault"

    assets = await adapter.fetch_assets("0xuser")

    # staked = 20, exit ticket assets=10 with 4 ready, 6 still queue → total 30 collateral
    assert any(
        asset.asset_address == adapter.eth_asset and asset.amount == 30
        for asset in assets
    )
    assert any(
        asset.asset_address == adapter.os_token_address and asset.amount == -4
        for asset in assets
    )


@pytest.mark.asyncio
async def test_stakewise_adapter_exit_queue_escrow(dummy_web3):
    adapter = _build_adapter(dummy_web3)

    escrow_ticket = ExitQueueTicket(
        ticket=2,
        shares=0,
        receiver=adapter.os_token_vault_escrow_address,
        block_number=12,
        log_index=0,
        timestamp=456,
        assets_hint=15,
    )

    async def tickets(_self, _context, _user):
        return [escrow_ticket]

    adapter._scan_exit_queue_tickets = tickets.__get__(adapter, StakeWiseAdapter)

    async def direct_rpc(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    adapter._rpc = direct_rpc.__get__(adapter, StakeWiseAdapter)

    async def fake_escrow(self, _vault_address, ticket):
        return (8, 6)

    adapter._fetch_escrow_state = fake_escrow.__get__(adapter, StakeWiseAdapter)

    shares_map = {"0xuser": 10}
    os_token_shares_map = {"0xuser": 4}

    dummy_contract = cast(
        Contract,
        SimpleNamespace(
            functions=SimpleNamespace(
                getShares=lambda account: _Call(shares_map.get(account, 0)),
                convertToAssets=lambda shares: _Call(shares * 2),
                osTokenPositions=lambda account: _Call(
                    os_token_shares_map.get(account, 0)
                ),
            ),
            events=DummyEvents(),
        ),
    )
    adapter.vault_contexts = [
        StakewiseVaultContext(address="0xvault", contract=dummy_contract, exit_events=[])
    ]
    adapter.vault_address = "0xvault"

    assets = await adapter.fetch_assets("0xuser")

    # staked=20, escrow ready=6 → collateral 26, liabilities include user (4) + escrow (8)
    assert any(
        asset.asset_address == adapter.eth_asset and asset.amount == 26
        for asset in assets
    )
    assert any(
        asset.asset_address == adapter.os_token_address and asset.amount == -12
        for asset in assets
    )
