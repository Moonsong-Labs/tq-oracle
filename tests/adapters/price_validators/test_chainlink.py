import pytest

from tq_oracle.adapters.price_validators.chainlink import ChainlinkValidator
from tq_oracle.adapters.price_adapters.cow_swap import CowSwapAdapter
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.config import OracleCLIConfig
from tq_oracle.config import Network


@pytest.fixture
def config():
    return OracleCLIConfig(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        l1_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
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


@pytest.fixture
def eth_address(config):
    address = config.assets["ETH"]
    assert address is not None
    return address


@pytest.fixture
def usdc_address(config):
    address = config.assets["USDC"]
    assert address is not None
    return address


@pytest.fixture
def usdt_address(config):
    address = config.assets["USDT"]
    assert address is not None
    return address


@pytest.fixture
def usds_address(config):
    address = config.assets["USDS"]
    assert address is not None
    return address


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
async def test_validate_prices_usdc_integration(config, eth_address, usdc_address):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=eth_address, prices={})
    price_data = await cow_swap_adapter.fetch_prices([usdc_address], price_data)

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_usdt_integration(config, eth_address, usdt_address):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=eth_address, prices={})
    price_data = await cow_swap_adapter.fetch_prices([usdt_address], price_data)

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_usds_integration(config, eth_address, usds_address):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=eth_address, prices={})
    price_data = await cow_swap_adapter.fetch_prices([usds_address], price_data)

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_all_stablecoins_integration(
    config, eth_address, usdc_address, usdt_address, usds_address
):
    validator = ChainlinkValidator(config)
    cow_swap_adapter = CowSwapAdapter(config)

    price_data = PriceData(base_asset=eth_address, prices={})
    price_data = await cow_swap_adapter.fetch_prices(
        [usdc_address, usdt_address, usds_address], price_data
    )

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_validate_prices_fails_on_excessive_deviation(
    config, eth_address, usdc_address
):
    validator = ChainlinkValidator(config)

    price_data = PriceData(
        base_asset=eth_address,
        prices={
            usdc_address: 1000000000000000,
        },
    )

    result = await validator.validate_prices(price_data)

    assert not result.passed
    assert "failure threshold" in result.message.lower()
    assert usdc_address in result.message


@pytest.mark.asyncio
async def test_validate_prices_passes_with_empty_prices(validator, eth_address):
    price_data = PriceData(base_asset=eth_address, prices={})

    result = await validator.validate_prices(price_data)

    assert result.passed
    assert "within acceptable deviation" in result.message.lower()
