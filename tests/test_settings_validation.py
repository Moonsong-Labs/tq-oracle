"""Tests for OracleSettings validation logic."""

import pytest
from pydantic import ValidationError

from tq_oracle.settings import Network, OracleSettings


def test_price_tolerance_positive_validation():
    """Test that price tolerances must be positive."""
    # Negative warning tolerance
    with pytest.raises(ValidationError, match="greater than 0"):
        OracleSettings(
            vault_address="0xVault",
            vault_rpc="https://eth.drpc.org",
            network=Network.MAINNET,
            price_warning_tolerance_percentage=-0.5,
        )

    # Zero failure tolerance
    with pytest.raises(ValidationError, match="greater than 0"):
        OracleSettings(
            vault_address="0xVault",
            vault_rpc="https://eth.drpc.org",
            network=Network.MAINNET,
            price_failure_tolerance_percentage=0,
        )


def test_price_tolerance_upper_bound_validation():
    """Test that price tolerances have reasonable upper bounds."""
    # Warning tolerance too high
    with pytest.raises(ValidationError, match="less than 100"):
        OracleSettings(
            vault_address="0xVault",
            vault_rpc="https://eth.drpc.org",
            network=Network.MAINNET,
            price_warning_tolerance_percentage=150.0,
        )

    # Failure tolerance too high
    with pytest.raises(ValidationError, match="less than 100"):
        OracleSettings(
            vault_address="0xVault",
            vault_rpc="https://eth.drpc.org",
            network=Network.MAINNET,
            price_failure_tolerance_percentage=1000.0,
        )


def test_price_tolerance_ordering_validation():
    """Test that warning tolerance must be less than failure tolerance."""
    # Warning equal to failure (invalid)
    with pytest.raises(
        ValueError,
        match="price_warning_tolerance_percentage.*must be less than.*price_failure_tolerance_percentage",
    ):
        OracleSettings(
            vault_address="0xVault",
            vault_rpc="https://eth.drpc.org",
            network=Network.MAINNET,
            price_warning_tolerance_percentage=1.0,
            price_failure_tolerance_percentage=1.0,
        )

    # Warning greater than failure (invalid)
    with pytest.raises(
        ValueError,
        match="price_warning_tolerance_percentage.*must be less than.*price_failure_tolerance_percentage",
    ):
        OracleSettings(
            vault_address="0xVault",
            vault_rpc="https://eth.drpc.org",
            network=Network.MAINNET,
            price_warning_tolerance_percentage=2.0,
            price_failure_tolerance_percentage=1.0,
        )


def test_valid_price_tolerance_configuration():
    """Test that valid price tolerance configurations are accepted."""
    # Default values should work
    config = OracleSettings(
        vault_address="0xVault",
        vault_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
    )
    assert config.price_warning_tolerance_percentage == 0.5
    assert config.price_failure_tolerance_percentage == 1.0

    # Custom valid values should work
    config = OracleSettings(
        vault_address="0xVault",
        vault_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
        price_warning_tolerance_percentage=0.1,
        price_failure_tolerance_percentage=0.5,
    )
    assert config.price_warning_tolerance_percentage == 0.1
    assert config.price_failure_tolerance_percentage == 0.5

    # Edge case: very small difference
    config = OracleSettings(
        vault_address="0xVault",
        vault_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
        price_warning_tolerance_percentage=0.1,
        price_failure_tolerance_percentage=0.101,
    )
    assert config.price_warning_tolerance_percentage == 0.1
    assert config.price_failure_tolerance_percentage == 0.101
