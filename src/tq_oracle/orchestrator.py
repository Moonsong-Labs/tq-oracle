from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import backoff
from web3 import Web3

from .constants import ETH_ASSET
from .adapters.price_adapters.base import BasePriceAdapter, PriceData
from .adapters import PRICE_ADAPTERS
from .adapters.asset_adapters import get_adapter_class
from .adapters.asset_adapters.base import AssetData, BaseAssetAdapter
from .adapters.asset_adapters.idle_balances import IdleBalancesAdapter
from .checks.pre_checks import PreCheckError, run_pre_checks
from .checks.price_validators import PriceValidationError, run_price_validations
from .logger import get_logger
from .processors import (
    compute_total_aggregated_assets,
    derive_final_prices,
    calculate_total_assets,
)
from .abi import load_vault_abi

from .report import generate_report, publish_report

if TYPE_CHECKING:
    from .config import OracleCLIConfig

logger = get_logger(__name__)


def _process_adapter_results(
    tasks_info: list[Any],
    results: tuple[BaseException | list[AssetData], ...],
    asset_data: list[list[AssetData]],
) -> None:
    """Process asyncio.gather results from adapter tasks.

    Args:
        tasks_info: List of task information tuples (varying structure)
        results: Results from asyncio.gather (may contain exceptions)
        asset_data: List to append successful asset results to
    """
    for task_info, result in zip(tasks_info, results):
        match result:
            case Exception() as e:
                if len(task_info) == 2:  # (name, _)
                    name = task_info[0]
                    logger.error("Adapter '%s' failed: %s", name, e)
                elif len(task_info) == 3:  # (subvault_addr, adapter, name)
                    subvault_addr, _, name = task_info
                    logger.error(
                        "Adapter '%s' failed for subvault %s: %s",
                        name,
                        subvault_addr,
                        e,
                    )
            case list() as assets:
                if len(task_info) == 2:  # (name, _)
                    name = task_info[0]
                    logger.debug("Adapter '%s' returned %d assets", name, len(assets))
                elif len(task_info) == 3:  # (subvault_addr, adapter, name)
                    subvault_addr, _, name = task_info
                    logger.debug(
                        "Adapter '%s' for subvault %s returned %d assets",
                        name,
                        subvault_addr,
                        len(assets),
                    )
                asset_data.append(assets)


async def _fetch_subvault_addresses(config: OracleCLIConfig) -> list[str]:
    """Discover all subvault addresses from the vault contract.

    Args:
        config: CLI configuration containing vault address and RPC endpoint

    Returns:
        List of subvault addresses
    """
    w3 = Web3(Web3.HTTPProvider(config.l1_rpc_required))
    vault_abi = load_vault_abi()
    vault_address = w3.to_checksum_address(config.vault_address_required)
    contract = w3.eth.contract(address=vault_address, abi=vault_abi)

    count = await asyncio.to_thread(contract.functions.subvaults().call)
    logger.debug("Vault has %d subvaults", count)

    # Fetch all subvault addresses in parallel to avoid thread pool exhaustion
    subvault_addresses = await asyncio.gather(
        *[
            asyncio.to_thread(contract.functions.subvaultAt(i).call)
            for i in range(count)
        ]
    )

    return list(subvault_addresses)


async def execute_oracle_flow(config: OracleCLIConfig) -> None:
    """Execute the complete oracle control flow.

    This implements the flowchart:
    1. Pre-checks (Safe validations + adapter checks)
    2. Fork: Parallel adapter queries
    3. Compute total assets
    4. Calculate relative prices
    5. Derive final prices via OracleHelper
    6. Generate report
    7. Publish (stdout if dry run, Safe if not)

    Args:
        config: CLI configuration containing all parameters
    """
    logger.info("Starting oracle flow for vault: %s", config.vault_address)
    logger.debug("Configuration: %s", config.as_safe_dict())

    logger.info(
        "Running pre-checks (max retries: %d, timeout: %.1fs)...",
        config.pre_check_retries,
        config.pre_check_timeout,
    )

    def _should_giveup(e: Exception) -> bool:
        """Determine if we should give up retrying based on the exception."""
        return isinstance(e, PreCheckError) and not e.retry_recommended

    def _on_backoff(details: Any) -> None:
        """Log retry attempts."""
        logger.warning(
            "Pre-check failed (attempt %d of %d): %s",
            details["tries"],
            config.pre_check_retries + 1,
            details.get("exception", details.get("value")),
        )

    def _on_giveup(details: Any) -> None:
        """Log when we give up retrying."""
        exc = details.get("exception", details.get("value"))
        if isinstance(exc, PreCheckError) and not exc.retry_recommended:
            logger.error("Pre-check failed (retry not recommended): %s", exc)
        else:
            logger.error(
                "Pre-checks failed after %d attempts: %s",
                details["tries"],
                exc,
            )

    @backoff.on_exception(
        backoff.constant,
        PreCheckError,
        max_tries=config.pre_check_retries + 1,
        interval=config.pre_check_timeout,
        giveup=_should_giveup,
        on_backoff=_on_backoff,
        on_giveup=_on_giveup,
    )
    async def _run_pre_checks_with_retry() -> None:
        """Run pre-checks with automatic retry on retriable errors."""
        await run_pre_checks(config, config.vault_address_required)

    await _run_pre_checks_with_retry()
    logger.info("Pre-checks passed successfully")

    logger.info("Discovering subvaults from vault contract...")
    subvault_addresses = await _fetch_subvault_addresses(config)
    logger.info("Found %d subvaults", len(subvault_addresses))

    # Validate subvault_adapters config references existing subvaults
    if config.subvault_adapters:
        normalized_subvault_addrs = {addr.lower() for addr in subvault_addresses}
        invalid_subvaults = [
            sv_config.subvault_address
            for sv_config in config.subvault_adapters
            if not sv_config.skip_subvault_existence_check
            and sv_config.subvault_address.lower() not in normalized_subvault_addrs
        ]

        if invalid_subvaults:
            raise ValueError(
                f"Config specifies adapters for non-existent subvaults: "
                f"{', '.join(invalid_subvaults)}"
            )

    # Collect asset fetching tasks
    logger.info("Setting up asset adapters...")
    asset_fetch_tasks = []

    # 1. Add default L1 idle_balances (runs against ALL subvaults unless globally skipped)
    #    Check if ANY subvault has skip_idle_balances=false (which means we should run it)
    should_run_default_idle_balances = any(
        not config.get_subvault_config(addr).skip_idle_balances
        for addr in subvault_addresses
    )

    if should_run_default_idle_balances:
        idle_l1_adapter = IdleBalancesAdapter(config, chain="l1")
        asset_fetch_tasks.append(
            ("idle_balances_l1", idle_l1_adapter.fetch_all_assets())
        )
        logger.debug("Added default L1 idle_balances adapter (all subvaults)")

    # 2. Add additional adapters per subvault
    def create_adapter_task(
        subvault_addr: str, adapter_name: str
    ) -> tuple[str, BaseAssetAdapter, str]:
        """Create an adapter instance for the given subvault and adapter name."""
        sv_config = config.get_subvault_config(subvault_addr)
        adapter_class = get_adapter_class(adapter_name)
        adapter = adapter_class(config, chain=sv_config.chain)

        logger.debug(
            "Subvault %s → additional adapter: %s (chain: %s)",
            subvault_addr,
            adapter_name,
            sv_config.chain,
        )
        return (subvault_addr, adapter, adapter_name)

    subvaults_to_process = set(subvault_addresses)

    if config.subvault_adapters:
        for sv_config in config.subvault_adapters:
            if sv_config.skip_subvault_existence_check:
                subvaults_to_process.add(sv_config.subvault_address)
                logger.debug(
                    "Including non-vault address for adapters: %s (skip_subvault_existence_check=true)",
                    sv_config.subvault_address,
                )

    adapter_tasks: list[tuple[str, BaseAssetAdapter, str]] = [
        create_adapter_task(subvault_addr, adapter_name)
        for subvault_addr in subvaults_to_process
        for adapter_name in config.get_subvault_config(
            subvault_addr
        ).additional_adapters
    ]

    # Fetch assets from all adapters in parallel
    logger.info(
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

    price_adapters: list[BasePriceAdapter] = [
        AdapterClass(config) for AdapterClass in PRICE_ADAPTERS
    ]

    asset_data: list[list[AssetData]] = []
    _process_adapter_results(asset_fetch_tasks, default_results, asset_data)
    _process_adapter_results(adapter_tasks, per_subvault_results, asset_data)

    logger.info("Computing agreggated assets...")
    aggregated = await compute_total_aggregated_assets(asset_data)
    logger.debug("Total aggregated assets: %d", len(aggregated.assets))

    asset_addresses = list(aggregated.assets)

    logger.info("Fetching prices for %d assets...", len(asset_addresses))
    price_data: PriceData = PriceData(base_asset=ETH_ASSET, prices={})
    for price_adapter in price_adapters:
        price_data = await price_adapter.fetch_prices(asset_addresses, price_data)
        logger.debug("Price adapter returned %d prices", len(price_data.prices))

    logger.info("Running price validations...")
    try:
        await run_price_validations(config, price_data)
        logger.info("Price validations passed successfully")
    except PriceValidationError as e:
        logger.error("Price validations failed: %s", e)
        raise

    logger.info("Calculating total assets in base asset...")
    total_assets = calculate_total_assets(aggregated, price_data)
    logger.debug("Total assets in base asset: %d", total_assets)

    logger.info("Deriving final prices via OracleHelper...")
    final_prices = await derive_final_prices(config, total_assets, price_data)

    logger.info("Generating report...")
    report = await generate_report(
        config.vault_address_required,
        aggregated,
        final_prices,
    )

    logger.info("Publishing report (dry_run=%s)...", config.dry_run)
    await publish_report(config, report)
    logger.info("Oracle flow completed successfully")
