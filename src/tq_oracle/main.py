"""CLI entrypoint for the TQ Oracle."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from .constants import (
    BASE_ORACLE_HELPER,
    DEFAULT_BASE_RPC_URL,
    DEFAULT_MAINNET_RPC_URL,
    DEFAULT_SEPOLIA_RPC_URL,
    HL_PROD_EVM_RPC,
    HL_TEST_EVM_RPC,
    MAINNET_ORACLE_HELPER,
    SEPOLIA_ORACLE_HELPER,
)
from .logger import setup_logging
from .settings import CCTPEnv, HyperliquidEnv, Network, OracleSettings
from .state import AppState

NETWORK_RPC_DEFAULTS = {
    Network.MAINNET: DEFAULT_MAINNET_RPC_URL,
    Network.SEPOLIA: DEFAULT_SEPOLIA_RPC_URL,
    Network.BASE: DEFAULT_BASE_RPC_URL,
}

NETWORK_ORACLE_HELPER_DEFAULTS = {
    Network.MAINNET: MAINNET_ORACLE_HELPER,
    Network.SEPOLIA: SEPOLIA_ORACLE_HELPER,
    Network.BASE: BASE_ORACLE_HELPER,
}

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    add_help_option=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_short=True,
    pretty_exceptions_show_locals=False,
    help="TVL reporting and Safe submission tool.",
)


def _build_logger() -> logging.Logger:
    """Build a logger instance."""
    return logging.getLogger("tq_oracle")


def _redacted_dump(settings: OracleSettings) -> dict:
    """Return settings as dict with secrets redacted."""
    return settings.as_safe_dict()


@app.callback()
def initialize_context(
    ctx: typer.Context,
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to a TOML config file (can include [tq_oracle] table).",
        ),
    ] = None,
    network: Annotated[
        Network | None,
        typer.Option(
            "--network",
            "-n",
            help="Network to use (mainnet, sepolia, or base).",
        ),
    ] = None,
    hyperliquid_env: Annotated[
        HyperliquidEnv | None,
        typer.Option(
            "--hyperliquid-env",
            help="Hyperliquid environment (mainnet or testnet); overrides env/config.",
        ),
    ] = None,
    cctp_env: Annotated[
        CCTPEnv | None,
        typer.Option(
            "--cctp-env",
            help="CCTP environment (mainnet or testnet); overrides env/config.",
        ),
    ] = None,
    dry_run: Annotated[
        bool | None,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Do not post onchain; overrides env/config.",
        ),
    ] = None,
    show_config: Annotated[
        bool,
        typer.Option(
            "--show-config",
            help="Print effective config (with secrets redacted) and exit.",
        ),
    ] = False,
):
    """Typer callback to initialize application state before any subcommand executes.

    This function runs automatically before commands like 'report'. It loads configuration,
    applies network-specific defaults, and stores the initialized AppState in ctx.obj
    for subcommands to access.
    """
    import os

    if config_path:
        os.environ["TQ_ORACLE_CONFIG"] = str(config_path)

    init_kwargs: dict[str, Network | HyperliquidEnv | CCTPEnv | bool] = {}
    if network is not None:
        init_kwargs["network"] = network
    if hyperliquid_env is not None:
        init_kwargs["hyperliquid_env"] = hyperliquid_env
    if cctp_env is not None:
        init_kwargs["cctp_env"] = cctp_env
    if dry_run is not None:
        init_kwargs["dry_run"] = dry_run

    settings = OracleSettings(**init_kwargs)

    used_default_vault_rpc = False
    if settings.vault_rpc is None:
        settings.vault_rpc = NETWORK_RPC_DEFAULTS[settings.network]
        used_default_vault_rpc = True

    if settings.oracle_helper_address is None:
        settings.oracle_helper_address = NETWORK_ORACLE_HELPER_DEFAULTS[
            settings.network
        ]

    default_hl_rpc = (
        HL_TEST_EVM_RPC if settings.hyperliquid_env == "testnet" else HL_PROD_EVM_RPC
    )

    used_default_hl_rpc = False
    if settings.hl_rpc is None:
        settings.hl_rpc = default_hl_rpc
        used_default_hl_rpc = True
    else:
        fields_set = getattr(settings, "model_fields_set", set())
        if "hl_rpc" not in fields_set and settings.hl_rpc == default_hl_rpc:
            used_default_hl_rpc = True

    settings.using_default_rpc = used_default_vault_rpc or used_default_hl_rpc

    setup_logging(settings.log_level)
    logger = _build_logger()

    ctx.obj = AppState(settings=settings, logger=logger)

    if show_config:
        typer.echo(json.dumps(_redacted_dump(settings), indent=2))
        raise typer.Exit(code=0)


@app.command()
def report(
    ctx: typer.Context,
    vault_address: Annotated[
        str | None, typer.Argument(help="Vault address to report.")
    ] = None,
):
    """Build a TVL report and (optionally) submit to Safe."""
    state: AppState = ctx.obj
    s = state.settings

    if vault_address:
        s.vault_address = vault_address

    if not s.vault_address:
        raise typer.BadParameter("vault_address must be configured")
    if not s.vault_rpc:
        raise typer.BadParameter("vault_rpc must be configured")
    if not s.oracle_helper_address:
        raise typer.BadParameter("oracle_helper_address must be configured")
    if not s.hl_rpc:
        raise typer.BadParameter("hl_rpc must be configured")

    if not s.dry_run:
        if not s.safe_address:
            raise typer.BadParameter(
                "safe_address is required when running with --no-dry-run.",
                param_hint=["--safe-address", "TQ_ORACLE_SAFE_ADDRESS"],
            )
        if not s.private_key:
            raise typer.BadParameter(
                "private_key is required when running with --no-dry-run.",
                param_hint=["--private-key", "TQ_ORACLE_PRIVATE_KEY"],
            )

    from .pipeline.run import run_report

    asyncio.run(run_report(state, s.vault_address_required))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
