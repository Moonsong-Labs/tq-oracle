import pytest

from tq_oracle.adapters.price_validators.positive_prices import PositivePricesValidator
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.config import OracleCLIConfig
from tq_oracle.constants import ETH_ASSET, USDC_MAINNET, USDT_MAINNET


@pytest.fixture
def config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://eth.drpc.org",
        safe_address=None,
        l1_subvault_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=False,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.fixture
def validator(config):
    return PositivePricesValidator(config)


@pytest.mark.asyncio
async def test_validate_prices_all_positive(validator):
    price_data = PriceData(
        base_asset=ETH_ASSET,
        prices={
            USDC_MAINNET: 1000000000000000,
            USDT_MAINNET: 1000000000000000,
        },
    )

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "all" in result.message.lower()
    assert "positive" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_prices_zero_price_fails(validator):
    price_data = PriceData(
        base_asset=ETH_ASSET,
        prices={
            USDC_MAINNET: 0,
            USDT_MAINNET: 1000000000000000,
        },
    )

    result = await validator.validate_prices(price_data)

    assert not result.passed
    assert "non-positive" in result.message.lower()
    assert USDC_MAINNET in result.message


@pytest.mark.asyncio
async def test_validate_prices_negative_price_fails(validator):
    price_data = PriceData(
        base_asset=ETH_ASSET,
        prices={
            USDC_MAINNET: -1000000000000000,
            USDT_MAINNET: 1000000000000000,
        },
    )

    result = await validator.validate_prices(price_data)

    assert not result.passed
    assert "non-positive" in result.message.lower()
    assert USDC_MAINNET in result.message


@pytest.mark.asyncio
async def test_validate_prices_multiple_invalid(validator):
    price_data = PriceData(
        base_asset=ETH_ASSET,
        prices={
            USDC_MAINNET: 0,
            USDT_MAINNET: -100,
        },
    )

    result = await validator.validate_prices(price_data)

    assert not result.passed
    assert "2" in result.message
    assert USDC_MAINNET in result.message
    assert USDT_MAINNET in result.message


@pytest.mark.asyncio
async def test_validate_prices_empty_data(validator):
    price_data = PriceData(base_asset=ETH_ASSET, prices={})

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "0" in result.message
