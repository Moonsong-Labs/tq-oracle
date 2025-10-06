from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from web3 import Web3
from web3.contract import Contract

from ..abi import load_oracle_helper_abi

if TYPE_CHECKING:
    from ..config import OracleCLIConfig
    from .price_calculator import RelativePrices


@dataclass
class FinalPrices:
    """Final oracle prices derived via OracleHelper contract."""

    prices: dict[str, int]  # asset_address -> final_price (18 decimals)


@dataclass
class EncodedAssetPrices:
    """Encoded asset prices."""

    asset_prices: list[tuple[str, int]]


async def derive_final_prices(
    config: OracleCLIConfig,
    total_assets: int,
    relative_prices: RelativePrices,
) -> FinalPrices:
    """Derive final prices via OracleHelper contract.

    Args:
        config: CLI configuration with RPC endpoints
        total_assets: Total assets from vault and adapters
        relative_prices: Relative prices from price calculator

    Returns:
        Final oracle prices

    This corresponds to the "Derive Final Prices via OracleHelper" step in the flowchart.
    """

    oracle_helper = get_oracle_helper_contract(config)

    vault = Web3.to_checksum_address(config.vault_address)
    asset_prices = encode_asset_prices(relative_prices)

    prices_array = oracle_helper.functions.getPricesD18(
        vault,
        total_assets,
        asset_prices.asset_prices,
    )

    prices = {asset_prices[i][0]: prices_array[i] for i in range(len(asset_prices))}

    return FinalPrices(prices=prices)


def get_oracle_helper_contract(config: OracleCLIConfig) -> Contract:
    w3 = Web3()
    abi = load_oracle_helper_abi()
    checksum_address = Web3.to_checksum_address(config.oracle_helper_address)
    return w3.eth.contract(address=checksum_address, abi=abi)


def encode_asset_prices(relative_prices: RelativePrices) -> EncodedAssetPrices:
    """Encode asset prices for OracleHelper contract."""
    asset_prices = sorted(relative_prices.prices.items(), key=lambda item: item[0])
    return EncodedAssetPrices(asset_prices=asset_prices)
