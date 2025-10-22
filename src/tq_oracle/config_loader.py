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

from .config import OracleCLIConfig, SubvaultAdapterConfig
from .adapters.asset_adapters import ADAPTER_REGISTRY


SECRET_FIELDS = {"private_key", "safe_txn_srvc_api_key"}


def parse_subvault_adapters(
    raw_configs: list[dict[str, Any]],
) -> list[SubvaultAdapterConfig]:
    """Parse and normalize subvault adapter configurations from TOML.

    Args:
        raw_configs: List of dicts from TOML [[subvault_adapters]] sections

    Returns:
        List of SubvaultAdapterConfig objects

    Raises:
        ValueError: If an invalid adapter name or chain is specified
    """

    def validate_and_normalize_adapter(adapter_name: Any) -> str:
        """Validate and normalize a single adapter name."""
        if not isinstance(adapter_name, str):
            raise ValueError(
                f"Invalid adapter specification: {adapter_name}. "
                "Must be a string (adapter name)."
            )
        normalized = adapter_name.lower()
        if normalized not in ADAPTER_REGISTRY:
            valid_adapters = ", ".join(ADAPTER_REGISTRY.keys())
            raise ValueError(
                f"Invalid adapter '{adapter_name}'. "
                f"Available adapters: {valid_adapters}"
            )
        return normalized

    def parse_single_config(raw_config: dict[str, Any]) -> SubvaultAdapterConfig:
        """Parse and validate a single subvault adapter configuration."""
        subvault_address = raw_config.get("subvault_address", "").lower()
        if not subvault_address:
            raise ValueError("subvault_address is required in [[subvault_adapters]]")

        chain = raw_config.get("chain", "l1").lower()
        if chain not in ("l1", "hyperliquid"):
            raise ValueError(
                f"Invalid chain '{chain}' for subvault {subvault_address}. "
                "Must be 'l1' or 'hyperliquid'."
            )

        additional_adapters_raw = raw_config.get("additional_adapters", [])
        skip_idle_balances = raw_config.get("skip_idle_balances", False)
        skip_subvault_existence_check = raw_config.get(
            "skip_subvault_existence_check", False
        )

        adapter_names = [
            validate_and_normalize_adapter(name) for name in additional_adapters_raw
        ]

        return SubvaultAdapterConfig(
            subvault_address=subvault_address,
            chain=chain,
            additional_adapters=adapter_names,
            skip_idle_balances=skip_idle_balances,
            skip_subvault_existence_check=skip_subvault_existence_check,
        )

    return [parse_single_config(raw_config) for raw_config in raw_configs]


def _check_for_secrets(data: dict[str, Any], path: str = "") -> None:
    """Recursively check dict for secret fields.

    Args:
        data: Dictionary to check
        path: Current path for error messages

    Raises:
        ValueError: If secret field found in TOML
    """
    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        if key in SECRET_FIELDS:
            raise ValueError(
                f"Security violation: '{key}' found in TOML config file at path '{current_path}'. "
                f"Secrets must only be provided via environment variables or CLI flags."
            )
        if isinstance(value, dict):
            _check_for_secrets(value, current_path)


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
        Dictionary of configuration values

    Raises:
        ValueError: If TOML file contains secret fields
    """
    with open(config_path, "rb") as f:
        raw_config = tomllib.load(f)

    _check_for_secrets(raw_config)

    if "subvault_adapters" in raw_config:
        raw_adapters = raw_config.pop("subvault_adapters")
        raw_config["subvault_adapters"] = parse_subvault_adapters(raw_adapters)

    return raw_config


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
    if val := os.getenv("LOG_LEVEL"):
        env_config["log_level"] = val

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
