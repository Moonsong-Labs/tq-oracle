import pytest
from decimal import Decimal

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.constants import ETH_ASSET
from tq_oracle.processors.oracle_helper import (
    encode_asset_prices,
    EncodedAssetPrices,
    derive_final_prices,
)
from tq_oracle.settings import OracleSettings


def test_encode_asset_prices_sorts_by_address():
    rp = PriceData(
        base_asset="0xBASE",
        prices={
            "0xBBB": Decimal(3),
            "0x111": Decimal(1),
            "0xAAA": Decimal(2),
        },
        decimals={
            "0xBBB": 6,
            "0x111": 18,
            "0xAAA": 8,
            "0xBASE": 18,
        },
    )

    encoded = encode_asset_prices(rp)

    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == [
        ("0x111", 10**18),
        ("0xAAA", 2 * 10**8),
        ("0xBBB", 3 * 10**6),
    ]


def test_encode_asset_prices_empty():
    rp = PriceData(base_asset="", prices={}, decimals={})
    encoded = encode_asset_prices(rp)
    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == []


def test_encode_asset_prices_single():
    rp = PriceData(
        base_asset="0xX",
        prices={"0xABC": Decimal(123)},
        decimals={"0xABC": 6, "0xX": 18},
    )
    encoded = encode_asset_prices(rp)
    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == [("0xABC", 123 * 10**6)]


def test_encode_asset_prices_preserves_fractional():
    rp = PriceData(
        base_asset="0xBASE",
        prices={"0x0000000000000000000000000000000000000ABC": Decimal("1.23456789")},
        decimals={
            "0x0000000000000000000000000000000000000ABC": 18,
            "0xBASE": 18,
        },
    )

    encoded = encode_asset_prices(rp)

    assert (
        dict(encoded.asset_prices)["0x0000000000000000000000000000000000000ABC"]
        == 1234567890000000000
    )


def test_encode_asset_prices_overwrites_base_asset_to_zero():
    rp = PriceData(
        base_asset=ETH_ASSET,
        prices={
            ETH_ASSET: Decimal(999999999),
            "0xAAA": Decimal(1000000000000000),
        },
        decimals={ETH_ASSET: 18, "0xAAA": 6},
    )
    encoded = encode_asset_prices(rp)

    prices_dict = dict(encoded.asset_prices)
    assert prices_dict[ETH_ASSET] == 0
    assert prices_dict["0xAAA"] == 1000000000000000 * 10**6


@pytest.mark.asyncio
async def test_derive_final_prices_excludes_tvl_only_assets(monkeypatch):
    captured_asset_prices: dict[str, list[tuple[str, int]]] = {}

    class FakeCall:
        def __init__(self, asset_prices: list[tuple[str, int]]):
            self._asset_prices = asset_prices

        def call(self, block_identifier: int):
            captured_asset_prices["asset_prices"] = self._asset_prices
            return [42] * len(self._asset_prices)

    class FakeContract:
        def __init__(self):
            self.functions = self

        def getPricesD18(self, _vault, _total_assets, asset_prices):
            return FakeCall(asset_prices)

    monkeypatch.setattr(
        "tq_oracle.processors.oracle_helper.get_oracle_helper_contract",
        lambda _config: FakeContract(),
    )

    config = OracleSettings(
        vault_address="0x0000000000000000000000000000000000000001",
        oracle_helper_address="0x0000000000000000000000000000000000000002",
        vault_rpc="https://example.com",
        block_number=123,
    )

    price_data = PriceData(
        base_asset="0x0000000000000000000000000000000000000001",
        prices={
            "0x0000000000000000000000000000000000000003": Decimal(10**18),
            "0x0000000000000000000000000000000000000004": Decimal(2 * 10**18),
        },
        decimals={
            "0x0000000000000000000000000000000000000003": 18,
            "0x0000000000000000000000000000000000000004": 18,
        },
    )

    excluded = {"0x0000000000000000000000000000000000000003"}

    result = await derive_final_prices(
        config,
        total_assets=100,
        price_data=price_data,
        excluded_assets=excluded,
    )

    assert captured_asset_prices["asset_prices"] == [
        ("0x0000000000000000000000000000000000000004", 2 * 10**36)
    ]
    assert result.prices == {
        "0x0000000000000000000000000000000000000004": 42,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_prices_d18_integration_via_derive_final_prices():
    provider = "https://eth.drpc.org"
    vault = "0x277C6A642564A91ff78b008022D65683cEE5CCC5"
    oracle_helper = "0x000000005F543c38d5ea6D0bF10A50974Eb55E35"
    total_assets = 666_555
    asset_prices = {
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": Decimal(3 * 10**18),
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": Decimal(10**18),
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE": Decimal(0),
    }

    config = OracleSettings(
        vault_address=vault,
        oracle_helper_address=oracle_helper,
        vault_rpc=provider,
        block_number=23690139,
        safe_address=None,
        safe_txn_srvc_api_key=None,
        dry_run=True,
        private_key=None,
    )

    relative_prices = PriceData(
        base_asset=vault,
        prices=asset_prices,
        decimals={
            "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": 18,
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": 18,
            "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE": 18,
        },
    )

    result = await derive_final_prices(config, total_assets, relative_prices)

    assert result.prices.keys() == {
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
    }

    assert all(isinstance(value, int) for value in result.prices.values())
