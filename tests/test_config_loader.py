"""Tests for configuration loader with TOML, ENV, and CLI precedence."""

import os
import tomllib
from pathlib import Path

import pytest

from tq_oracle.config_loader import (
    build_config,
    find_config_file,
    load_env_vars,
    load_toml_config,
    merge_config_sources,
)


def test_find_config_file_explicit_path(tmp_path):
    """Should find config file from explicit path."""
    config_file = tmp_path / "custom-config.toml"
    config_file.write_text("[rpc]\nl1_rpc = 'test'")

    result = find_config_file(str(config_file))
    assert result == config_file


def test_find_config_file_explicit_path_not_found():
    """Should raise FileNotFoundError if explicit path doesn't exist."""
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        find_config_file("/nonexistent/config.toml")


def test_find_config_file_current_directory(tmp_path, monkeypatch):
    """Should find tq-oracle.toml in current directory."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "tq-oracle.toml"
    config_file.write_text("[rpc]\nl1_rpc = 'test'")

    result = find_config_file()
    # Path objects compare equal regardless of absolute/relative
    assert result is not None
    assert result.name == "tq-oracle.toml"
    assert result.exists()


def test_find_config_file_user_config_directory(tmp_path, monkeypatch):
    """Should find config.toml in user config directory."""
    # Mock home directory
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Create user config directory and file
    user_config_dir = fake_home / ".config" / "tq-oracle"
    user_config_dir.mkdir(parents=True)
    config_file = user_config_dir / "config.toml"
    config_file.write_text("[rpc]\nl1_rpc = 'test'")

    # Change to different directory (not where local config would be)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    result = find_config_file()
    assert result == config_file


def test_find_config_file_none_if_not_found(tmp_path, monkeypatch):
    """Should return None if no config file found."""
    monkeypatch.chdir(tmp_path)
    result = find_config_file()
    assert result is None


def test_load_toml_config_basic(tmp_path):
    """Should load and flatten basic TOML config."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
testnet = true

[rpc]
l1_rpc = "https://sepolia.example.com"
hl_rpc = "https://hl.example.com"
max_calls = 5
max_concurrent_calls = 10
delay = 0.2
jitter = 0.05

[subvaults]
l1_subvault_address = "0xL1SUB"
hl_subvault_address = "0xHLSUB"

[safe]
address = "0xSAFE"
dry_run = false

[checks]
ignore_empty_vault = true
ignore_timeout = true
ignore_active_proposal = false
retries = 5
timeout = 15.0
"""
    )

    result = load_toml_config(config_file)

    assert result["vault_address"] == "0xVAULT"
    assert result["testnet"] is True
    assert result["l1_rpc"] == "https://sepolia.example.com"
    assert result["hl_rpc"] == "https://hl.example.com"
    assert result["max_calls"] == 5
    assert result["rpc_max_concurrent_calls"] == 10
    assert result["rpc_delay"] == 0.2
    assert result["rpc_jitter"] == 0.05
    assert result["l1_subvault_address"] == "0xL1SUB"
    assert result["hl_subvault_address"] == "0xHLSUB"
    assert result["safe_address"] == "0xSAFE"
    assert result["dry_run"] is False
    assert result["ignore_empty_vault"] is True
    assert result["ignore_timeout_check"] is True
    assert result["ignore_active_proposal_check"] is False
    assert result["pre_check_retries"] == 5
    assert result["pre_check_timeout"] == 15.0


def test_load_toml_config_rejects_secrets(tmp_path):
    """Should raise ValueError if TOML contains secret fields."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
private_key = "0xSECRET"
"""
    )

    with pytest.raises(ValueError, match="Security violation.*private_key"):
        load_toml_config(config_file)


def test_load_toml_config_rejects_safe_api_key(tmp_path):
    """Should raise ValueError if TOML contains safe API key."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
safe_txn_srvc_api_key = "secret_key"
"""
    )

    with pytest.raises(ValueError, match="Security violation.*safe_txn_srvc_api_key"):
        load_toml_config(config_file)


def test_load_toml_config_rejects_nested_secrets(tmp_path):
    """Should raise ValueError if TOML contains secrets in nested sections."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"

[safe]
address = "0xSAFE"
private_key = "0xNESTED_SECRET"
"""
    )

    with pytest.raises(
        ValueError,
        match=r"Security violation: 'private_key' found.*at path 'safe\.private_key'",
    ):
        load_toml_config(config_file)


def test_load_toml_config_handles_malformed_toml(tmp_path):
    """Should raise TOMLDecodeError for invalid TOML syntax."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'vault_address = "0xVAULT\n[rpc]\nl1_rpc = "no-closing-quote'
    )

    with pytest.raises(tomllib.TOMLDecodeError):
        load_toml_config(config_file)


def test_load_toml_config_handles_empty_file(tmp_path):
    """Should return an empty dict for an empty TOML file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("")

    result = load_toml_config(config_file)
    assert result == {}


def test_load_toml_config_ignores_unknown_fields(tmp_path):
    """Should ignore unknown fields and sections in the TOML file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
unknown_top_level = "should be ignored"

[rpc]
l1_rpc = "https://eth.example.com"

[unknown_section]
key = "value"
"""
    )

    result = load_toml_config(config_file)

    # Check that known fields are loaded
    assert result["vault_address"] == "0xVAULT"
    assert result["l1_rpc"] == "https://eth.example.com"
    # Check that unknown fields are NOT loaded
    assert "unknown_top_level" not in result
    assert "key" not in result


def test_load_env_vars(monkeypatch):
    """Should load configuration from environment variables."""
    monkeypatch.setenv("L1_RPC", "https://eth-from-env.com")
    monkeypatch.setenv("HL_EVM_RPC", "https://hl-from-env.com")
    monkeypatch.setenv("L1_SUBVAULT_ADDRESS", "0xL1ENV")
    monkeypatch.setenv("HL_SUBVAULT_ADDRESS", "0xHLENV")
    monkeypatch.setenv("PRIVATE_KEY", "0xPRIVATE")
    monkeypatch.setenv("SAFE_TRANSACTION_SERVICE_API_KEY", "api_key_123")

    result = load_env_vars()

    assert result["l1_rpc"] == "https://eth-from-env.com"
    assert result["hl_rpc"] == "https://hl-from-env.com"
    assert result["l1_subvault_address"] == "0xL1ENV"
    assert result["hl_subvault_address"] == "0xHLENV"
    assert result["private_key"] == "0xPRIVATE"
    assert result["safe_txn_srvc_api_key"] == "api_key_123"


def test_load_env_vars_empty_when_not_set():
    """Should return empty dict when no env vars are set."""
    # Clear any existing env vars
    for key in [
        "L1_RPC",
        "HL_EVM_RPC",
        "L1_SUBVAULT_ADDRESS",
        "HL_SUBVAULT_ADDRESS",
        "PRIVATE_KEY",
        "SAFE_TRANSACTION_SERVICE_API_KEY",
    ]:
        os.environ.pop(key, None)

    result = load_env_vars()
    assert result == {}


def test_merge_config_sources_cli_wins():
    """CLI arguments should have highest precedence."""
    toml_config = {"l1_rpc": "https://toml.com", "testnet": False}
    env_vars = {"l1_rpc": "https://env.com"}
    cli_args = {"l1_rpc": "https://cli.com"}

    result = merge_config_sources(cli_args, env_vars, toml_config)

    assert result["l1_rpc"] == "https://cli.com"  # CLI wins


def test_merge_config_sources_env_wins_over_toml():
    """ENV vars should override TOML config."""
    toml_config = {"l1_rpc": "https://toml.com", "testnet": False}
    env_vars = {"l1_rpc": "https://env.com"}
    cli_args = {}

    result = merge_config_sources(cli_args, env_vars, toml_config)

    assert result["l1_rpc"] == "https://env.com"  # ENV wins
    assert result["testnet"] is False  # TOML value preserved


def test_merge_config_sources_toml_default():
    """TOML values should be used when CLI and ENV don't provide them."""
    toml_config = {"l1_rpc": "https://toml.com", "testnet": True}
    env_vars = {}
    cli_args = {}

    result = merge_config_sources(cli_args, env_vars, toml_config)

    assert result["l1_rpc"] == "https://toml.com"
    assert result["testnet"] is True


def test_merge_config_sources_cli_none_values_ignored():
    """CLI None values should not override ENV or TOML."""
    toml_config = {"l1_rpc": "https://toml.com"}
    env_vars = {"hl_rpc": "https://env.com"}
    cli_args = {"l1_rpc": None, "hl_rpc": None}  # None values from CLI

    result = merge_config_sources(cli_args, env_vars, toml_config)

    # None values shouldn't override
    assert result["l1_rpc"] == "https://toml.com"
    assert result["hl_rpc"] == "https://env.com"


def test_build_config_full_precedence(tmp_path, monkeypatch):
    """Test full precedence chain: CLI > ENV > TOML."""
    # Create TOML config
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xTOML"
testnet = false

[rpc]
l1_rpc = "https://toml.com"
hl_rpc = "https://hl-toml.com"
"""
    )

    # Set environment variables
    monkeypatch.setenv("L1_RPC", "https://env.com")
    monkeypatch.setenv("PRIVATE_KEY", "0xPRIVATE")

    # Build config with CLI args
    cfg = build_config(
        config_file_path=str(config_file),
        vault_address="0xCLI",
        l1_rpc="https://cli.com",
    )

    # Verify precedence
    assert cfg.vault_address == "0xCLI"  # CLI wins
    assert cfg.l1_rpc == "https://cli.com"  # CLI wins
    assert cfg.hl_rpc == "https://hl-toml.com"  # TOML (no override)
    assert cfg.private_key == "0xPRIVATE"  # ENV (not in TOML or CLI)
    assert cfg.testnet is False  # TOML (no override)


def test_build_config_without_toml_file(monkeypatch):
    """Should work without TOML file using ENV and CLI only."""
    monkeypatch.setenv("L1_RPC", "https://env.com")

    cfg = build_config(vault_address="0xCLI", testnet=True)

    assert cfg.vault_address == "0xCLI"
    assert cfg.l1_rpc == "https://env.com"
    assert cfg.testnet is True


def test_build_config_minimal():
    """Should work with minimal configuration using all defaults."""
    cfg = build_config(vault_address="0xMINIMAL")

    assert cfg.vault_address == "0xMINIMAL"
    assert cfg.dry_run is True  # Default
    assert cfg.testnet is False  # Default
    assert cfg.pre_check_retries == 3  # Default


def test_build_config_partial_toml(tmp_path):
    """Should work with TOML file containing only some sections."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"

[rpc]
l1_rpc = "https://eth.example.com"
# Only one section, missing [subvaults], [safe], [checks]
"""
    )

    cfg = build_config(config_file_path=str(config_file))

    # Verify partial config is loaded
    assert cfg.vault_address == "0xVAULT"
    assert cfg.l1_rpc == "https://eth.example.com"
    # Verify defaults still apply for missing sections
    assert cfg.dry_run is True  # Default
    assert cfg.pre_check_retries == 3  # Default
