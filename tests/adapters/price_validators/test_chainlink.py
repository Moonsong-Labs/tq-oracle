import pytest

from tq_oracle.adapters.price_validators.chainlink import ChainlinkValidator
from tq_oracle.adapters.price_adapters.cow_swap import CowSwapAdapter
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.config import OracleCLIConfig
from tq_oracle.constants import ETH_ASSET, USDC_MAINNET, USDT_MAINNET, USDS_MAINNET


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
        chainlink_price_warning_tolerance_percentage=0.5,
        chainlink_price_failure_tolerance_percentage=1.0,
    )


@pytest.fixture
def validator(config):
    return ChainlinkValidator(config)


def test_calculate_price_deviation_percentage_no_deviation(validator):
    result = validator._calculate_price_deviation_percentage(
        reference_price=1000,
        actual_price=1000,
    )
    assert result == 0.0


def test_calculate_price_deviation_percentage_positive_deviation(validator):
    result = validator._calculate_price_deviation_percentage(
        reference_price=1100,
        actual_price=1000,
    )
    assert result == 10.0


def test_calculate_price_deviation_percentage_negative_deviation(validator):
    result = validator._calculate_price_deviation_percentage(
        reference_price=900,
        actual_price=1000,
    )
    assert result == 10.0


def test_calculate_price_deviation_percentage_large_numbers(validator):
    result = validator._calculate_price_deviation_percentage(
        reference_price=1_000_000_000_000_000_000,
        actual_price=950_000_000_000_000_000,
    )
    assert result == pytest.approx(5.263157894736842, rel=1e-6)


def test_calculate_price_deviation_percentage_zero_actual_price_raises_error(validator):
    with pytest.raises(ValueError, match="actual_price cannot be zero"):
        validator._calculate_price_deviation_percentage(
            reference_price=1000,
            actual_price=0,
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_usdc_integration(config):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=ETH_ASSET, prices={})
    price_data = await cow_swap_adapter.fetch_prices([USDC_MAINNET], price_data)

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_usdt_integration(config):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=ETH_ASSET, prices={})
    price_data = await cow_swap_adapter.fetch_prices([USDT_MAINNET], price_data)

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_usds_integration(config):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=ETH_ASSET, prices={})
    price_data = await cow_swap_adapter.fetch_prices([USDS_MAINNET], price_data)

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_all_stablecoins_integration(config):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=ETH_ASSET, prices={})
    price_data = await cow_swap_adapter.fetch_prices(
        [USDC_MAINNET, USDT_MAINNET, USDS_MAINNET], price_data
    )

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_fails_on_excessive_deviation(config):
    validator = ChainlinkValidator(config)

    price_data = PriceData(
        base_asset=ETH_ASSET,
        prices={
            USDC_MAINNET: 1000000000000000,
        },
    )

    result = await validator.validate_prices(price_data)

    assert not result.passed
    assert "failure threshold" in result.message.lower()
    assert USDC_MAINNET in result.message


@pytest.mark.asyncio
async def test_validate_prices_passes_with_empty_prices(validator):
    price_data = PriceData(base_asset=ETH_ASSET, prices={})

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


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
