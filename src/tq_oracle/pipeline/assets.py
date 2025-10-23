"""Asset collection from various adapters."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from web3 import Web3

from ..adapters.asset_adapters import get_adapter_class
from ..adapters.asset_adapters.base import AssetData
from ..adapters.asset_adapters.idle_balances import IdleBalancesAdapter
from ..abi import load_vault_abi
from ..processors import compute_total_aggregated_assets

if TYPE_CHECKING:
    from ..state import AppState
    from ..processors import AggregatedAssets


async def _fetch_subvault_addresses(state: AppState) -> list[str]:
    """Discover all subvault addresses from the vault contract.

    Args:
        state: Application state containing settings

    Returns:
        List of subvault addresses
    """
    s = state.settings
    log = state.logger

    w3 = Web3(Web3.HTTPProvider(s.l1_rpc_required))
    vault_abi = load_vault_abi()
    vault_address = w3.to_checksum_address(s.vault_address_required)
    contract = w3.eth.contract(address=vault_address, abi=vault_abi)

    count = await asyncio.to_thread(contract.functions.subvaults().call)
    log.debug("Vault has %d subvaults", count)

    # Fetch all subvault addresses in parallel to avoid thread pool exhaustion
    subvault_addresses = await asyncio.gather(
        *[
            asyncio.to_thread(contract.functions.subvaultAt(i).call)
            for i in range(count)
        ]
    )

    return list(subvault_addresses)


def _process_adapter_results(
    tasks_info: list[Any],
    results: tuple[BaseException | list[AssetData], ...],
    asset_data: list[list[AssetData]],
    log: Any,
) -> None:
    """Process asyncio.gather results from adapter tasks.

    Args:
        tasks_info: List of task information tuples (varying structure)
        results: Results from asyncio.gather (may contain exceptions)
        asset_data: List to append successful asset results to
        log: Logger instance
    """
    for task_info, result in zip(tasks_info, results):
        match result:
            case Exception() as e:
                if len(task_info) == 2:  # (name, _)
                    name = task_info[0]
                    log.error("Adapter '%s' failed: %s", name, e)
                elif len(task_info) == 3:  # (subvault_addr, adapter, name)
                    subvault_addr, _, name = task_info
                    log.error(
                        "Adapter '%s' failed for subvault %s: %s",
                        name,
                        subvault_addr,
                        e,
                    )
            case list() as assets:
                if len(task_info) == 2:  # (name, _)
                    name = task_info[0]
                    log.debug("Adapter '%s' returned %d assets", name, len(assets))
                elif len(task_info) == 3:  # (subvault_addr, adapter, name)
                    subvault_addr, _, name = task_info
                    log.debug(
                        "Adapter '%s' for subvault %s returned %d assets",
                        name,
                        subvault_addr,
                        len(assets),
                    )
                asset_data.append(assets)


async def collect_assets(state: AppState) -> AggregatedAssets:
    """Collect assets from all configured adapters.

    Args:
        state: Application state containing settings and logger

    Returns:
        AggregatedAssets containing all collected assets
    """
    s = state.settings
    log = state.logger

    log.info("Discovering subvaults from vault contract...")
    subvault_addresses = await _fetch_subvault_addresses(state)
    log.info("Found %d subvaults", len(subvault_addresses))

    # Validate subvault_adapters config references existing subvaults
    if s.subvault_adapters:
        normalized_subvault_addrs = {addr.lower() for addr in subvault_addresses}
        invalid_subvaults = [
            sv_config["subvault_address"]
            for sv_config in s.subvault_adapters
            if not sv_config.get("skip_subvault_existence_check", False)
            and sv_config["subvault_address"].lower() not in normalized_subvault_addrs
        ]

        if invalid_subvaults:
            raise ValueError(
                f"Config specifies adapters for non-existent subvaults: "
                f"{', '.join(invalid_subvaults)}"
            )

    # Collect asset fetching tasks
    log.info("Setting up asset adapters...")
    asset_fetch_tasks = []

    # Helper to get subvault config
    def get_subvault_config(subvault_address: str) -> dict[str, Any]:
        """Get adapter configuration for a specific subvault."""
        normalized_address = subvault_address.lower()
        for config in s.subvault_adapters:
            if config["subvault_address"].lower() == normalized_address:
                return config
        # Return default config
        return {
            "subvault_address": subvault_address,
            "chain": "l1",
            "additional_adapters": [],
            "skip_idle_balances": False,
        }

    # 1. Add default L1 idle_balances (runs against ALL subvaults unless globally skipped)
    should_run_default_idle_balances = any(
        not get_subvault_config(addr).get("skip_idle_balances", False)
        for addr in subvault_addresses
    )

    if should_run_default_idle_balances:
        idle_l1_adapter = IdleBalancesAdapter(s, chain="l1")
        asset_fetch_tasks.append(
            ("idle_balances_l1", idle_l1_adapter.fetch_all_assets())
        )
        log.debug("Added default L1 idle_balances adapter (all subvaults)")

    # 2. Add additional adapters per subvault
    def create_adapter_task(
        subvault_addr: str, adapter_name: str
    ) -> tuple[str, Any, str]:
        """Create an adapter instance for the given subvault and adapter name."""
        sv_config = get_subvault_config(subvault_addr)
        adapter_class = get_adapter_class(adapter_name)
        adapter = adapter_class(s, chain=sv_config.get("chain", "l1"))

        log.debug(
            "Subvault %s → additional adapter: %s (chain: %s)",
            subvault_addr,
            adapter_name,
            sv_config.get("chain", "l1"),
        )
        return (subvault_addr, adapter, adapter_name)

    subvaults_to_process = set(subvault_addresses)

    if s.subvault_adapters:
        for sv_config in s.subvault_adapters:
            if sv_config.get("skip_subvault_existence_check", False):
                subvaults_to_process.add(sv_config["subvault_address"])
                log.debug(
                    "Including non-vault address for adapters: %s (skip_subvault_existence_check=true)",
                    sv_config["subvault_address"],
                )

    adapter_tasks: list[tuple[str, Any, str]] = [
        create_adapter_task(subvault_addr, adapter_name)
        for subvault_addr in subvaults_to_process
        for adapter_name in get_subvault_config(subvault_addr).get(
            "additional_adapters", []
        )
    ]

    # Fetch assets from all adapters in parallel
    log.info(
        "Fetching assets: %d adapter tasks + %d additional per-subvault tasks...",
        len(asset_fetch_tasks),
        len(adapter_tasks),
    )

    # Execute default adapters
    default_results = await asyncio.gather(
        *[task for _, task in asset_fetch_tasks], return_exceptions=True
    )

    # Execute per-subvault adapters
    per_subvault_results = await asyncio.gather(
        *[
            adapter.fetch_assets(subvault_addr)
            for subvault_addr, adapter, _ in adapter_tasks
        ],
        return_exceptions=True,
    )

    asset_data: list[list[AssetData]] = []
    _process_adapter_results(asset_fetch_tasks, default_results, asset_data, log)
    _process_adapter_results(adapter_tasks, per_subvault_results, asset_data, log)

    log.info("Computing aggregated assets...")
    aggregated = await compute_total_aggregated_assets(asset_data)
    log.debug("Total aggregated assets: %d", len(aggregated.assets))

    return aggregated
