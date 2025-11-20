"""Oracle Reports timeout check adapter."""

from __future__ import annotations

import logging

from web3 import AsyncWeb3

from tq_oracle.abi import load_oracle_abi
from tq_oracle.adapters.check_adapters.base import BaseCheckAdapter, CheckResult
from tq_oracle.settings import OracleSettings

logger = logging.getLogger(__name__)


def format_time_remaining(seconds: int) -> str:
    """Format seconds into human-readable time.

    Args:
        seconds: Number of seconds to format

    Returns:
        Formatted time string (e.g., "2h 15m", "45m 30s", "30s")
    """
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    elif seconds >= 60:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s"
    else:
        return f"{seconds}s"


class TimeoutCheckAdapter(BaseCheckAdapter):
    """Check if timeout period has elapsed since last oracle report."""

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self._config = config

    @property
    def name(self) -> str:
        return "Oracle Timeout Check"

    async def run_check(self) -> CheckResult:
        """Check if timeout period has elapsed since last report.

        If config.ignore_timeout_check is True, this will PASS with a warning
        message instead of FAILING when timeout hasn't elapsed.

        Returns:
            CheckResult indicating if submission is allowed
        """
        w3 = None
        try:
            w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._config.vault_rpc))
            block_number = self._config.block_number_required

            oracle_address = self._config.oracle_address
            logger.debug(f"Using oracle address: {oracle_address}")

            oracle_abi = load_oracle_abi()
            oracle_checksum = w3.to_checksum_address(oracle_address)
            oracle = w3.eth.contract(address=oracle_checksum, abi=oracle_abi)

            supported_count = await oracle.functions.supportedAssets().call(
                block_identifier=block_number
            )

            if supported_count == 0:
                return CheckResult(
                    passed=True,
                    message="No supported assets configured, skipping timeout check",
                )

            # only looking at first asset since we do global reports
            first_asset = await oracle.functions.supportedAssetAt(0).call(
                block_identifier=block_number
            )
            logger.debug(f"Checking timeout for asset: {first_asset}")
            (
                _price_d18,
                last_report_timestamp,
                _is_suspicious,
            ) = await oracle.functions.getReport(first_asset).call(
                block_identifier=block_number
            )

            if last_report_timestamp == 0:
                return CheckResult(
                    passed=True, message="No previous report exists, submission allowed"
                )

            (
                _max_abs_deviation,
                _sus_abs__deviation,
                _max_rel_deviation,
                _sus_rel_deviation,
                timeout,
                _deposit_interval,
                _redeem_interval,
            ) = await oracle.functions.securityParams().call(
                block_identifier=block_number
            )

            block_info = await w3.eth.get_block(block_number)
            current_timestamp = block_info["timestamp"]

            next_valid_time = last_report_timestamp + timeout
            can_submit = current_timestamp >= next_valid_time

            if can_submit:
                return CheckResult(
                    passed=True,
                    message="Timeout period elapsed, submission allowed",
                    retry_recommended=False,
                )
            else:
                seconds_remaining = next_valid_time - current_timestamp
                time_msg = format_time_remaining(seconds_remaining)

                if self._config.ignore_timeout_check:
                    return CheckResult(
                        passed=True,
                        message=f"Timeout not elapsed ({time_msg} remaining) - WARNING: proceeding anyway due to --ignore-timeout-check flag",
                        retry_recommended=False,
                    )
                else:
                    return CheckResult(
                        passed=False,
                        message=f"Cannot submit - {time_msg} remaining until next valid submission",
                        retry_recommended=False,
                    )

        except Exception as e:
            logger.error(f"Error checking oracle timeout: {e}")
            return CheckResult(
                passed=False,
                message=f"Error checking oracle timeout: {str(e)}",
                retry_recommended=False,
            )
        finally:
            if w3:
                try:
                    await w3.provider.disconnect()  # type: ignore[union-attr]
                except AttributeError as e:
                    logger.debug(
                        f"Provider disconnect expected (no disconnect method): {e}"
                    )
