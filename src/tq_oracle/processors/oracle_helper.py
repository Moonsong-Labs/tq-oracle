from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError

from ..abi import load_oracle_helper_abi
from ..logger import get_logger
from ..adapters.price_adapters.base import PriceData

if TYPE_CHECKING:
    from ..settings import OracleSettings

logger = get_logger(__name__)


@dataclass
class FinalPrices:
    """Final oracle prices derived via OracleHelper contract."""

    prices: dict[str, int]  # asset_address -> final_price (18 decimals)


@dataclass
class EncodedAssetPrices:
    """Encoded asset prices."""

    asset_prices: list[tuple[str, int]]


async def derive_final_prices(
    config: OracleSettings,
    total_assets: int,
    price_data: PriceData,
) -> FinalPrices:
    """Derive final prices via OracleHelper contract.

    Args:
        config: CLI configuration with RPC endpoints
        total_assets: Total assets from vault and adapters
        price_data: Prices from price adapters

    Returns:
        Final oracle prices

    This corresponds to the "Derive Final Prices via OracleHelper" step in the flowchart.
    """

    oracle_helper = get_oracle_helper_contract(config)

    vault = Web3.to_checksum_address(config.vault_address)
    asset_prices = encode_asset_prices(price_data).asset_prices

    try:
        prices_array = oracle_helper.functions.getPricesD18(
            vault,
            total_assets,
            asset_prices,
        ).call(block_identifier="latest")

        prices = {asset_prices[i][0]: prices_array[i] for i in range(len(asset_prices))}

        return FinalPrices(prices=prices)
    except ContractLogicError as e:
        if config.ignore_empty_vault and "asset not found" in str(e):
            logger.warning(
                "OracleHelper contract returned 'asset not found' error. "
                "Returning zero prices due to --ignore-empty-vault flag."
            )
            prices = {asset: 0 for asset, _ in asset_prices}
            return FinalPrices(prices=prices)
        else:
            raise


def get_oracle_helper_contract(config: OracleSettings) -> Contract:
    w3 = Web3(Web3.HTTPProvider(config.l1_rpc))
    abi = load_oracle_helper_abi()
    checksum_address = Web3.to_checksum_address(config.oracle_helper_address)
    return w3.eth.contract(address=checksum_address, abi=abi)


def encode_asset_prices(prices: PriceData) -> EncodedAssetPrices:
    """Encode asset prices for OracleHelper contract.

    Python's default string sort is case-sensitive and doesn't match Solidity's behavior.
    """
    # Always sets the base asset to price 0
    if prices.base_asset in prices.prices:
        prices.prices[prices.base_asset] = 0
    # Sorts addresses numerically (as integers) to match Solidity's address comparison
    asset_prices = sorted(prices.prices.items(), key=lambda item: int(item[0], 16))
    return EncodedAssetPrices(asset_prices=asset_prices)
