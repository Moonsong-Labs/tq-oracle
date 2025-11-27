"""Rich console formatter for dry run reports."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text

from .generator import OracleReport
from ..constants import ETH_MAINNET_ASSETS, SEPOLIA_ASSETS, BASE_ASSETS


# Reverse lookup: address -> symbol
def _build_address_to_symbol() -> dict[str, str]:
    """Build reverse lookup from address to symbol."""
    result: dict[str, str] = {}
    for assets in [ETH_MAINNET_ASSETS, SEPOLIA_ASSETS, BASE_ASSETS]:
        for symbol, addr in assets.items():
            if isinstance(addr, str):
                result[addr.lower()] = symbol
    return result


_ADDRESS_TO_SYMBOL: dict[str, str] = _build_address_to_symbol()


def _get_symbol(address: str) -> str:
    """Get symbol for an address, or truncated address if unknown."""
    return _ADDRESS_TO_SYMBOL.get(address.lower(), f"{address[:6]}...{address[-4:]}")


def _format_wei(wei: int) -> str:
    """Format wei value to human-readable ETH amount."""
    return f"{wei / 1e18:.6f}"


def _format_wei_compact(wei: int) -> str:
    """Format wei value compactly with comma separators."""
    return f"{wei:,}"


def _truncate_address(address: str) -> str:
    """Truncate address for display."""
    return f"{address[:10]}...{address[-4:]}"


def format_report_table(report: OracleReport, encoded_calldata: bytes) -> None:
    """Print rich formatted two-column dashboard to stdout.

    Args:
        report: The oracle report to format
        encoded_calldata: The encoded calldata for the transaction
    """
    console = Console()

    # Build vault info table
    vault_table = Table(show_header=False, box=None, padding=(0, 1))
    vault_table.add_column("Key", style="dim")
    vault_table.add_column("Value", style="cyan")
    vault_table.add_row("Address", _truncate_address(report.vault_address))
    vault_table.add_row("Base Asset", _get_symbol(report.base_asset))
    vault_table.add_row("Network", "mainnet")  # Could be derived from settings

    vault_panel = Panel(vault_table, title="[bold]Vault Info[/]", border_style="blue")

    # Build summary table
    summary_table = Table(show_header=False, box=None, padding=(0, 1))
    summary_table.add_column("Key", style="dim")
    summary_table.add_column("Value", style="green")
    summary_table.add_row("Total Shares", _format_wei(report.total_shares))
    summary_table.add_row("TVL", f"{_format_wei(report.tvl_in_base_asset)} ETH")
    summary_table.add_row("Assets", str(len(report.total_assets)))

    summary_panel = Panel(summary_table, title="[bold]Summary[/]", border_style="green")

    # Top row: two columns
    top_row = Columns([vault_panel, summary_panel], equal=True, expand=True)

    # Build asset breakdown table
    asset_table = Table(title=None, expand=True, show_lines=False)
    asset_table.add_column("Asset", style="cyan", no_wrap=True)
    asset_table.add_column("Balance (wei)", justify="right", style="dim")
    asset_table.add_column("Balance", justify="right")
    asset_table.add_column("Adapter Price", justify="right", style="yellow")
    asset_table.add_column("Final Price", justify="right", style="yellow")
    asset_table.add_column("Value (ETH)", justify="right", style="green")

    total_value = Decimal(0)
    total_balance_units = Decimal(0)
    for addr, balance in report.total_assets.items():
        symbol = _get_symbol(addr)
        balance_wei = f"{balance:,}"
        balance_units = Decimal(balance) / Decimal(1e18)
        balance_units_display = f"{balance_units:.12f}"
        total_balance_units += balance_units

        # Get adapter price (stored as string representation of Decimal)
        adapter_price_str = report.adapter_prices.get(addr, "0")
        try:
            adapter_price = Decimal(adapter_price_str)
            adapter_price_display = f"{adapter_price:.12f}"
        except Exception:
            adapter_price = Decimal(0)
            adapter_price_display = "—"

        # Get final price (stored as int, 18 decimals)
        # Show <N/A> if asset not in final_prices
        if addr in report.final_prices:
            final_price = report.final_prices[addr]
            final_price_human = _format_wei(final_price)
        else:
            final_price_human = "[dim]<N/A>[/]"

        # Calculate value in base asset (ETH terms)
        # adapter_price is price per smallest unit (wei) in D18
        # balance is in wei
        # value = balance * adapter_price
        value = Decimal(balance) * adapter_price
        value_eth = value / Decimal(1e18)
        value_human = f"{value_eth:.12f}"
        total_value += value_eth

        asset_table.add_row(
            symbol,
            balance_wei,
            balance_units_display,
            adapter_price_display,
            final_price_human,
            value_human,
        )

    # Add total row
    asset_table.add_row(
        "[bold]TOTAL[/]",
        "",
        f"[bold]{total_balance_units:.6f}[/]",
        "",
        "",
        f"[bold]{total_value:.6f}[/]",
        style="bold",
    )

    asset_panel = Panel(
        asset_table,
        title="[bold]Asset Breakdown[/]",
        border_style="cyan",
    )

    # Calldata panel (full, with word wrap)
    calldata_hex = encoded_calldata.hex()
    calldata_panel = Panel(
        Text(calldata_hex, style="dim", overflow="fold"),
        title="[bold]Calldata[/]",
        border_style="dim",
    )

    # Build the full dashboard
    outer_panel = Panel(
        Group(top_row, "", asset_panel, "", calldata_panel),
        title="[bold white]TQ Oracle Dry Run[/]",
        border_style="white",
        padding=(1, 2),
    )

    console.print()
    console.print(outer_panel)
    console.print()
