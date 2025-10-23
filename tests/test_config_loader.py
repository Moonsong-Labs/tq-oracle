"""Tests for config_loader module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tq_oracle.config_loader import (
    build_config,
    find_config_file,
    load_env_vars,
    load_toml_config,
    merge_config_sources,
)

if TYPE_CHECKING:
    pass


def test_find_config_file_explicit_path(tmp_path: Path):
    """Should find config file when explicit path is provided."""
    config_file = tmp_path / "my-config.toml"
    config_file.write_text("testnet = true\n")

    result = find_config_file(str(config_file))
    assert result == config_file


def test_find_config_file_explicit_path_not_found():
    """Should raise FileNotFoundError when explicit path doesn't exist."""
    with pytest.raises(FileNotFoundError):
        find_config_file("/nonexistent/path/config.toml")


def test_find_config_file_current_directory(tmp_path: Path, monkeypatch):
    """Should find tq-oracle.toml in current directory."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "tq-oracle.toml"
    config_file.write_text("testnet = true\n")

    result = find_config_file()
    assert result is not None
    assert result.resolve() == config_file.resolve()


def test_find_config_file_user_config_directory(tmp_path: Path, monkeypatch):
    """Should find config.toml in ~/.config/tq-oracle/ directory."""
    # Create fake home directory
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # Create config in user config directory
    config_dir = fake_home / ".config" / "tq-oracle"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    config_file.write_text("testnet = true\n")

    # Change to a different directory
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    result = find_config_file()
    assert result == config_file


def test_find_config_file_none_if_not_found(tmp_path: Path, monkeypatch):
    """Should return None when no config file is found."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = find_config_file()
    assert result is None


def test_load_toml_config_basic(tmp_path: Path):
    """Should load basic TOML configuration."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
testnet = true
l1_rpc = "https://sepolia.example.com"
hl_rpc = "https://hl.example.com"
max_calls = 5
rpc_max_concurrent_calls = 10
rpc_delay = 0.2
rpc_jitter = 0.05
l1_subvault_address = "0xL1SUB"
hl_subvault_address = "0xHLSUB"
safe_address = "0xSAFE"
dry_run = false
ignore_empty_vault = true
ignore_timeout_check = true
ignore_active_proposal_check = false
pre_check_retries = 5
pre_check_timeout = 15.0
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


def test_load_toml_config_rejects_secrets(tmp_path: Path):
    """Should reject TOML files containing private_key."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('private_key = "0xSECRET"\n')

    with pytest.raises(ValueError, match="private_key"):
        load_toml_config(config_file)


def test_load_toml_config_rejects_safe_api_key(tmp_path: Path):
    """Should reject TOML files containing safe_txn_srvc_api_key."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('safe_txn_srvc_api_key = "secret-key"\n')

    with pytest.raises(ValueError, match="safe_txn_srvc_api_key"):
        load_toml_config(config_file)


def test_load_toml_config_rejects_nested_secrets(tmp_path: Path):
    """Should reject TOML files with secrets in nested structures."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"

[[subvault_adapters]]
subvault_address = "0xSUB"
private_key = "0xSECRET"
"""
    )

    with pytest.raises(ValueError, match="private_key"):
        load_toml_config(config_file)


def test_load_toml_config_handles_malformed_toml(tmp_path: Path):
    """Should raise appropriate error for malformed TOML."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("invalid [ toml {")

    with pytest.raises(ValueError):
        load_toml_config(config_file)


def test_load_toml_config_handles_empty_file(tmp_path: Path):
    """Should handle empty TOML file gracefully."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("")

    result = load_toml_config(config_file)
    assert result == {}


def test_load_toml_config_ignores_unknown_fields(tmp_path: Path):
    """Should ignore unknown TOML fields (allows for comments/future fields)."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
unknown_field = "should be ignored"
"""
    )

    result = load_toml_config(config_file)
    assert "vault_address" in result
    assert "unknown_field" in result  # We don't filter, OracleCLIConfig will handle


def test_load_env_vars(monkeypatch):
    """Should load configuration from environment variables."""
    monkeypatch.setenv("L1_RPC", "https://env-eth.example.com")
    monkeypatch.setenv("HL_EVM_RPC", "https://env-hl.example.com")
    monkeypatch.setenv("HL_SUBVAULT_ADDRESS", "0xENVSUB")

    result = load_env_vars()

    assert result["l1_rpc"] == "https://env-eth.example.com"
    assert result["hl_rpc"] == "https://env-hl.example.com"
    assert result["hl_subvault_address"] == "0xENVSUB"


def test_load_env_vars_empty_when_not_set():
    """Should return empty dict when no env vars are set."""
    # Ensure test env vars are not set
    for key in ["L1_RPC", "HL_EVM_RPC", "HL_SUBVAULT_ADDRESS"]:
        os.environ.pop(key, None)

    result = load_env_vars()
    assert result == {}


def test_merge_config_sources_cli_wins():
    """CLI arguments should take precedence over env and TOML."""
    cli_args = {"l1_rpc": "https://cli.example.com"}
    env_vars = {"l1_rpc": "https://env.example.com"}
    toml_config = {"l1_rpc": "https://toml.example.com"}

    result = merge_config_sources(cli_args, env_vars, toml_config)
    assert result["l1_rpc"] == "https://cli.example.com"


def test_merge_config_sources_env_wins_over_toml():
    """Environment variables should take precedence over TOML."""
    cli_args = {}
    env_vars = {"l1_rpc": "https://env.example.com"}
    toml_config = {"l1_rpc": "https://toml.example.com"}

    result = merge_config_sources(cli_args, env_vars, toml_config)
    assert result["l1_rpc"] == "https://env.example.com"


def test_merge_config_sources_toml_default():
    """TOML should be used when no CLI or env override."""
    cli_args = {}
    env_vars = {}
    toml_config = {"l1_rpc": "https://toml.example.com"}

    result = merge_config_sources(cli_args, env_vars, toml_config)
    assert result["l1_rpc"] == "https://toml.example.com"


def test_merge_config_sources_cli_none_values_ignored():
    """CLI arguments with None values should be ignored."""
    cli_args = {"l1_rpc": None}
    env_vars = {}
    toml_config = {"l1_rpc": "https://toml.example.com"}

    result = merge_config_sources(cli_args, env_vars, toml_config)
    assert result["l1_rpc"] == "https://toml.example.com"


def test_build_config_full_precedence(tmp_path: Path, monkeypatch):
    """Test full precedence chain: CLI > ENV > TOML."""
    # Set up TOML config
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xTOML"
l1_rpc = "https://toml.example.com"
hl_rpc = "https://toml-hl.example.com"
testnet = false
"""
    )

    # Set up ENV vars
    monkeypatch.setenv("L1_RPC", "https://env.example.com")

    # Build config with CLI override
    cfg = build_config(
        config_file_path=str(config_file),
        l1_rpc="https://cli.example.com",
    )

    # CLI should win for l1_rpc
    assert cfg.l1_rpc == "https://cli.example.com"

    # TOML values where no override
    assert cfg.vault_address == "0xTOML"
    assert cfg.hl_rpc == "https://toml-hl.example.com"
    assert cfg.testnet is False


def test_build_config_without_toml_file():
    """Should work without a TOML file (CLI + ENV only)."""
    cfg = build_config(
        vault_address="0xCLI",
        testnet=True,
        l1_rpc="https://cli.example.com",
    )

    assert cfg.vault_address == "0xCLI"
    assert cfg.testnet is True
    assert cfg.l1_rpc == "https://cli.example.com"


def test_build_config_minimal():
    """Should work with minimal configuration using all defaults."""
    cfg = build_config(vault_address="0xMINIMAL")

    assert cfg.vault_address == "0xMINIMAL"
    assert cfg.dry_run is True  # Default
    assert cfg.testnet is False  # Default
    assert cfg.pre_check_retries == 3  # Default


def test_build_config_partial_toml(tmp_path):
    """Should work with TOML file containing only some fields."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
l1_rpc = "https://eth.example.com"
# Only some fields, missing others
"""
    )

    cfg = build_config(config_file_path=str(config_file))

    # Verify partial config is loaded
    assert cfg.vault_address == "0xVAULT"
    assert cfg.l1_rpc == "https://eth.example.com"
    # Verify defaults still apply for missing sections
    assert cfg.dry_run is True  # Default
    assert cfg.pre_check_retries == 3  # Default


def test_toml_boolean_overrides_cli_default(tmp_path: Path) -> None:
    """Test that TOML boolean values override CLI defaults.

    This is a regression test for the bug where CLI default values
    (e.g., ignore_timeout_check=False) would override TOML config
    values (e.g., ignore_timeout_check=true).
    """
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
ignore_timeout_check = true
ignore_empty_vault = true
dry_run = false
"""
    )

    # Simulate CLI invocation with default values (as if user didn't pass flags)
    result = build_config(
        config_file_path=str(config_file),
        ignore_timeout_check=False,  # CLI default
        ignore_empty_vault=False,  # CLI default
        dry_run=True,  # CLI default
    )

    # TOML values should win over CLI defaults
    assert result.ignore_timeout_check is True, "TOML should override CLI default"
    assert result.ignore_empty_vault is True, "TOML should override CLI default"
    assert result.dry_run is False, "TOML should override CLI default"


def test_explicit_cli_overrides_toml(tmp_path: Path) -> None:
    """Test that explicit non-default CLI values override TOML.

    When a user explicitly sets a CLI flag to a non-default value,
    it should override TOML config.
    """
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
vault_address = "0xVAULT"
ignore_timeout_check = false
pre_check_retries = 5
"""
    )

    # Simulate CLI invocation with non-default explicit values
    result = build_config(
        config_file_path=str(config_file),
        ignore_timeout_check=True,  # Non-default CLI value
        pre_check_retries=10,  # Non-default CLI value
    )

    # Explicit non-default CLI values should override TOML
    assert result.ignore_timeout_check is True, "Non-default CLI should override TOML"
    assert result.pre_check_retries == 10, "Non-default CLI should override TOML"
