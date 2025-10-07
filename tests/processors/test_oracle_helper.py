import pytest

from tq_oracle.processors.price_calculator import RelativePrices
from tq_oracle.processors.oracle_helper import (
    encode_asset_prices,
    EncodedAssetPrices,
    derive_final_prices,
)
from tq_oracle.config import OracleCLIConfig


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


def test_encode_asset_prices_empty():
    rp = RelativePrices(base_asset="", prices={})
    encoded = encode_asset_prices(rp)
    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == []


def test_encode_asset_prices_single():
    rp = RelativePrices(base_asset="0xX", prices={"0xABC": 123})
    encoded = encode_asset_prices(rp)
    assert isinstance(encoded, EncodedAssetPrices)
    assert encoded.asset_prices == [("0xABC", 123)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_prices_d18_integration_via_derive_final_prices():
    provider = "https://eth.drpc.org"
    vault = "0x277C6A642564A91ff78b008022D65683cEE5CCC5"
    oracle_helper = "0x000000005F543c38d5ea6D0bF10A50974Eb55E35"
    total_assets = 666_555
    asset_prices = {
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": 3 * 10**18,
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": 10**18,
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE": 0,
    }

    config = OracleCLIConfig(
        vault_address=vault,
        oracle_helper_address=oracle_helper,
        l1_rpc=provider,
        safe_address=None,
        safe_txn_srvc_api_key=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=True,
        private_key=None,
    )

    relative_prices = RelativePrices(base_asset=vault, prices=asset_prices)

    result = await derive_final_prices(config, total_assets, relative_prices)

    assert result.prices.keys() == {
        "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
    }

    assert all(isinstance(value, int) for value in result.prices.values())
