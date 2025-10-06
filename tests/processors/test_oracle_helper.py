import pytest

from tq_oracle.processors.price_calculator import RelativePrices
from tq_oracle.processors.oracle_helper import (
    encode_asset_prices,
    EncodedAssetPrices,
)


@pytest.mark.asyncio
def test_encode_asset_prices_sorts_by_address():
    rp = RelativePrices(
        base_asset="0xBASE",
        prices={
            "0xBBB": 3,
            "0x111": 1,
            "0xAAA": 2,
        },
    )

    encoded = encode_asset_prices(rp)

    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == [
        ("0x111", 1),
        ("0xAAA", 2),
        ("0xBBB", 3),
    ]


@pytest.mark.asyncio
def test_encode_asset_prices_empty():
    rp = RelativePrices(base_asset="", prices={})
    encoded = encode_asset_prices(rp)
    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == []


@pytest.mark.asyncio
def test_encode_asset_prices_single():
    rp = RelativePrices(base_asset="0xX", prices={"0xABC": 123})
    encoded = encode_asset_prices(rp)
    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == [("0xABC", 123)]
