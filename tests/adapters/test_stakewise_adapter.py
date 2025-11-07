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
                getVaultState=lambda *_: _Call((40, 12)),
                isStrategyProxyExiting=lambda *_: _Call(True),
                getProxyExitState=lambda *_: _Call((5, 4)),
            )
        ),
    )

    assets = await adapter.fetch_assets(user)

    eth_amount = sum(
        asset.amount for asset in assets if asset.asset_address == adapter.eth_asset
    )
    os_amount = sum(
        asset.amount
        for asset in assets
        if asset.asset_address == adapter.os_token_address
    )

    # (20 + 40 + 5) - 11 = 54 net ETH exposure
    assert eth_amount == 54
    # (21 + 12) - 17 shares = 16 net osETH (assets - liabilities in shares)
    assert os_amount == 16

    # Ensure liabilities are represented with negative entries
    assert any(
        asset.amount < 0 and asset.asset_address == adapter.eth_asset
        for asset in assets
    )
    assert any(
        asset.amount < 0 and asset.asset_address == adapter.os_token_address
        for asset in assets
    )
