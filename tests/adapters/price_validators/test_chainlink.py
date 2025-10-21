import pytest

from tq_oracle.adapters.price_validators.chainlink import ChainlinkValidator
from tq_oracle.config import OracleCLIConfig


@pytest.fixture
def validator():
    config = OracleCLIConfig(
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
