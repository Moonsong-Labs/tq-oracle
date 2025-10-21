"""Configuration loader with support for TOML files, environment variables, and CLI arguments.

Precedence order (highest to lowest):
1. CLI arguments
2. Environment variables
3. TOML configuration file
4. Dataclass defaults
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Optional

from .config import OracleCLIConfig


SECRET_FIELDS = {"private_key", "safe_txn_srvc_api_key"}


def find_config_file(config_path: Optional[str] = None) -> Optional[Path]:
    """Find configuration file using standard search paths.

    Search order:
    1. Explicit path from --config flag
    2. ./tq-oracle.toml (current directory)
    3. ~/.config/tq-oracle/config.toml (user config directory)

    Args:
        config_path: Explicit path to config file (from CLI --config flag)

    Returns:
        Path to config file if found, None otherwise
    """
    if config_path:
        path = Path(config_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Check current directory
    local_config = Path("tq-oracle.toml")
    if local_config.exists():
        return local_config

    # Check user config directory
    user_config = Path.home() / ".config" / "tq-oracle" / "config.toml"
    if user_config.exists():
        return user_config

    return None


def load_toml_config(config_path: Path) -> dict[str, Any]:
    """Load and parse TOML configuration file.

    Args:
        config_path: Path to TOML configuration file

    Returns:
        Flat dictionary of configuration values (sections flattened)

    Raises:
        ValueError: If TOML file contains secret fields
    """
    with open(config_path, "rb") as f:
        raw_config = tomllib.load(f)

    # Security check: ensure no secrets in TOML (check all levels)
    def check_for_secrets(data: dict[str, Any], path: str = "") -> None:
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if key in SECRET_FIELDS:
                raise ValueError(
                    f"Security violation: '{key}' found in TOML config file at path '{current_path}'. "
                    f"Secrets must only be provided via environment variables or CLI flags."
                )
            if isinstance(value, dict):
                check_for_secrets(value, current_path)

    check_for_secrets(raw_config)

    flat_config: dict[str, Any] = {}

    if "vault_address" in raw_config:
        flat_config["vault_address"] = raw_config["vault_address"]
    if "oracle_helper_address" in raw_config:
        flat_config["oracle_helper_address"] = raw_config["oracle_helper_address"]
    if "testnet" in raw_config:
        flat_config["testnet"] = raw_config["testnet"]

    if "rpc" in raw_config:
        rpc = raw_config["rpc"]
        if "l1_rpc" in rpc:
            flat_config["l1_rpc"] = rpc["l1_rpc"]
        if "hl_rpc" in rpc:
            flat_config["hl_rpc"] = rpc["hl_rpc"]
        if "max_calls" in rpc:
            flat_config["max_calls"] = rpc["max_calls"]
        if "max_concurrent_calls" in rpc:
            flat_config["rpc_max_concurrent_calls"] = rpc["max_concurrent_calls"]
        if "delay" in rpc:
            flat_config["rpc_delay"] = rpc["delay"]
        if "jitter" in rpc:
            flat_config["rpc_jitter"] = rpc["jitter"]

    if "subvaults" in raw_config:
        subvaults = raw_config["subvaults"]
        if "l1_subvault_address" in subvaults:
            flat_config["l1_subvault_address"] = subvaults["l1_subvault_address"]
        if "hl_subvault_address" in subvaults:
            flat_config["hl_subvault_address"] = subvaults["hl_subvault_address"]

    if "safe" in raw_config:
        safe = raw_config["safe"]
        if "address" in safe:
            flat_config["safe_address"] = safe["address"]
        if "dry_run" in safe:
            flat_config["dry_run"] = safe["dry_run"]

    if "checks" in raw_config:
        checks = raw_config["checks"]
        if "ignore_empty_vault" in checks:
            flat_config["ignore_empty_vault"] = checks["ignore_empty_vault"]
        if "ignore_timeout" in checks:
            flat_config["ignore_timeout_check"] = checks["ignore_timeout"]
        if "ignore_active_proposal" in checks:
            flat_config["ignore_active_proposal_check"] = checks[
                "ignore_active_proposal"
            ]
        if "retries" in checks:
            flat_config["pre_check_retries"] = checks["retries"]
        if "timeout" in checks:
            flat_config["pre_check_timeout"] = checks["timeout"]

    return flat_config


def load_env_vars() -> dict[str, Any]:
    """Load configuration from environment variables.

    Returns:
        Dictionary of configuration values from environment
    """
    env_config: dict[str, Any] = {}

    if val := os.getenv("L1_RPC"):
        env_config["l1_rpc"] = val
    if val := os.getenv("HL_EVM_RPC"):
        env_config["hl_rpc"] = val
    if val := os.getenv("L1_SUBVAULT_ADDRESS"):
        env_config["l1_subvault_address"] = val
    if val := os.getenv("HL_SUBVAULT_ADDRESS"):
        env_config["hl_subvault_address"] = val
    if val := os.getenv("PRIVATE_KEY"):
        env_config["private_key"] = val
    if val := os.getenv("SAFE_TRANSACTION_SERVICE_API_KEY"):
        env_config["safe_txn_srvc_api_key"] = val

    return env_config


def merge_config_sources(
    cli_args: dict[str, Any],
    env_vars: dict[str, Any],
    toml_config: dict[str, Any],
) -> dict[str, Any]:
    """Merge configuration from all sources with proper precedence.

    Precedence (highest to lowest):
    1. CLI arguments
    2. Environment variables
    3. TOML configuration file

    Args:
        cli_args: Arguments from CLI (non-None values only)
        env_vars: Configuration from environment variables
        toml_config: Configuration from TOML file

    Returns:
        Merged configuration dictionary
    """
    merged = toml_config.copy()

    for key, value in env_vars.items():
        merged[key] = value

    for key, value in cli_args.items():
        if value is not None:
            merged[key] = value

    return merged


def build_config(
    config_file_path: Optional[str] = None,
    **cli_args: Any,
) -> OracleCLIConfig:
    """Build OracleCLIConfig from all configuration sources.

    This is the main entry point for configuration loading.
    Handles precedence: CLI → ENV → TOML → Defaults

    Args:
        config_file_path: Optional explicit path to config file
        **cli_args: CLI arguments (only non-None values should be passed)

    Returns:
        Fully configured OracleCLIConfig instance
    """
    toml_config: dict[str, Any] = {}
    config_path = find_config_file(config_file_path)
    if config_path:
        toml_config = load_toml_config(config_path)

    env_vars = load_env_vars()

    merged = merge_config_sources(cli_args, env_vars, toml_config)

    return OracleCLIConfig(**merged)
