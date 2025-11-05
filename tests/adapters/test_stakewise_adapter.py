from types import SimpleNamespace
from typing import Any, cast

import pytest

from tq_oracle.adapters.asset_adapters.stakewise import StakeWiseAdapter
from tq_oracle.settings import OracleSettings


@pytest.mark.asyncio
async def test_stakewise_adapter_collects_balances(monkeypatch):
    class DummyWeb3:
        HTTPProvider = staticmethod(lambda *_args, **_kwargs: None)

        def __init__(self, _provider):
            self.eth = SimpleNamespace(
                contract=lambda *_args, **_kwargs: SimpleNamespace(
                    functions=SimpleNamespace()
                )
            )

        def is_connected(self) -> bool:  # pragma: no cover - trivial
            return True

        @staticmethod
        def to_checksum_address(value: str) -> str:  # pragma: no cover - trivial
            return value

    monkeypatch.setattr(
        "tq_oracle.adapters.asset_adapters.stakewise.Web3",
        DummyWeb3,
    )

    config = OracleSettings(
        vault_rpc="http://localhost",
        block_number=1,
        vault_address="0x0000000000000000000000000000000000000001",
        stakewise_vault_address="0x0000000000000000000000000000000000000002",
        stakewise_os_token_vault_controller="0x0000000000000000000000000000000000000003",
        stakewise_leverage_strategy_address="0x0000000000000000000000000000000000000004",
        stakewise_debt_asset="0x0000000000000000000000000000000000000005",
        stakewise_os_token_address="0x0000000000000000000000000000000000000006",
    )

    adapter = StakeWiseAdapter(config)

    user = adapter.w3.to_checksum_address("0x0000000000000000000000000000000000000007")
    proxy = adapter.w3.to_checksum_address("0x0000000000000000000000000000000000000008")

    shares_map = {user: 10, proxy: 20}
    os_token_shares_map = {user: 5, proxy: 7}

    async def fake_vault_shares(self, account):
        return shares_map.get(account, 0)

    async def fake_vault_assets(self, shares):
        return shares * 2

    async def fake_os_token_shares(self, account):
        return os_token_shares_map.get(account, 0)

    async def fake_os_token_assets(self, shares):
        return shares * 3

    async def direct_rpc(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    adapter._vault_shares = fake_vault_shares.__get__(adapter, StakeWiseAdapter)
    adapter._vault_assets = fake_vault_assets.__get__(adapter, StakeWiseAdapter)
    adapter._os_token_shares = fake_os_token_shares.__get__(adapter, StakeWiseAdapter)
    adapter._os_token_assets = fake_os_token_assets.__get__(adapter, StakeWiseAdapter)
    adapter._rpc = direct_rpc.__get__(adapter, StakeWiseAdapter)

    class _Call:
        def __init__(self, result):
            self._result = result

        def call(self, *args, **kwargs):
            return self._result

    adapter.strategy = cast(
        Any,
        SimpleNamespace(
            functions=SimpleNamespace(
                getStrategyProxy=lambda *_: _Call(proxy),
                getBorrowState=lambda *_: _Call((11, 7)),
            )
        ),
    )

    assets = await adapter.fetch_assets(user)

    assert len(assets) == 4
    eth_asset = next(a for a in assets if a.asset_address == adapter.eth_asset)
    os_token_assets = [
        a for a in assets if a.asset_address == adapter.os_token_address
    ]
    debt_asset = next(a for a in assets if a.asset_address == adapter.debt_asset)

    assert eth_asset.amount == 60  # (10 + 20) * 2
    # Held osToken (supplied shares only in test): 7 * 3 = 21
    held_entry = next(a for a in os_token_assets if a.amount > 0)
    assert held_entry.amount == 21
    # Minted osToken debt: (5 + 7) * 3 = 36, recorded as liability
    debt_entry = next(a for a in os_token_assets if a.amount < 0)
    assert debt_entry.amount == -36
    # Borrowed assets are treated as liabilities
    assert debt_asset.amount == -11
