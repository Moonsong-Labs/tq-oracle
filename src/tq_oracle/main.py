"""CLI entrypoint for the TQ Oracle."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from .constants import (
    DEFAULT_MAINNET_RPC_URL,
    DEFAULT_SEPOLIA_RPC_URL,
    HL_PROD_EVM_RPC,
    HL_TEST_EVM_RPC,
    MAINNET_ORACLE_HELPER,
    SEPOLIA_ORACLE_HELPER,
)
from .logger import setup_logging
from .settings import OracleSettings
from .state import AppState

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
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
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to a TOML config file (can include [tq_oracle] table).",
        ),
    ] = None,
    testnet: Annotated[
        bool,
        typer.Option(
            "--testnet/--no-testnet", help="Use testnet; overrides env/config."
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Do not post onchain; overrides env/config.",
        ),
    ] = True,
    show_config: Annotated[
        bool,
        typer.Option(
            "--show-config",
            help="Print effective config (with secrets redacted) and exit.",
        ),
    ] = False,
):
    """Initialize application state once and pass it to subcommands via ctx.obj."""
    import os

    if config:
        os.environ["TQ_ORACLE_CONFIG"] = str(config)

    settings = OracleSettings(
        testnet=testnet,
        dry_run=dry_run,
    )

    if settings.l1_rpc is None:
        settings.l1_rpc = (
            DEFAULT_SEPOLIA_RPC_URL if settings.testnet else DEFAULT_MAINNET_RPC_URL
        )
    if settings.oracle_helper_address is None:
        settings.oracle_helper_address = (
            SEPOLIA_ORACLE_HELPER if settings.testnet else MAINNET_ORACLE_HELPER
        )
    if settings.hl_rpc is None:
        settings.hl_rpc = HL_PROD_EVM_RPC if not settings.testnet else HL_TEST_EVM_RPC

    settings.using_default_rpc = config is None or settings.hl_rpc is None

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
    if not s.l1_rpc:
        raise typer.BadParameter("l1_rpc must be configured")
    if not s.oracle_helper_address:
        raise typer.BadParameter("oracle_helper_address must be configured")
    if not s.hl_rpc:
        raise typer.BadParameter("hl_rpc must be configured")

    if not s.dry_run and not s.safe_address and not s.private_key:
        raise typer.BadParameter(
            "Either safe_address OR private_key required when running with --no-dry-run.",
            param_hint=["TQ_ORACLE_SAFE_ADDRESS", "TQ_ORACLE_PRIVATE_KEY"],
        )

    if s.safe_address and not s.dry_run and not s.private_key:
        raise typer.BadParameter(
            "private_key required when using safe_address with --no-dry-run.",
            param_hint=["TQ_ORACLE_PRIVATE_KEY"],
        )

    from .pipeline.run import run_report

    asyncio.run(run_report(state, s.vault_address_required))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
