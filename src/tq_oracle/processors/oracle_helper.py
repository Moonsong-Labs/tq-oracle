from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError

from ..abi import load_oracle_helper_abi
from ..adapters.price_adapters.base import PriceData
from ..logger import get_logger
from ..settings import OracleSettings

logger = get_logger(__name__)

# From OracleHelper.sol:
# Price of the asset expressed via the base asset.
# If the price is 0, it means that the asset is the base asset, then for other assets:
# If priceD18 = 1e18, it means that 1 asset = 1 base asset
# If priceD18 = 0.5e18, it means that 1 asset = 0.5 base asset
# If priceD18 = 2e18, it means that 1 asset = 2 base assets


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
    excluded_assets: set[str] | None = None,
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
    logger.debug(f"Calling OracleHelper at {config.oracle_helper_address}")
    logger.debug(f"Vault address: {vault}")
    logger.debug(f"Total assets (D18): {total_assets}")
    logger.debug(f"Asset prices (scaled to whole tokens): {asset_prices}")
    if excluded_assets:
        excluded_lower = {addr.lower() for addr in excluded_assets}
        asset_prices = [
            (addr, price)
            for addr, price in asset_prices
            if addr.lower() not in excluded_lower
        ]
    block_number = config.block_number_required

    try:
        prices_array = oracle_helper.functions.getPricesD18(
            vault,
            total_assets,
            asset_prices,
        ).call(block_identifier=block_number)

        prices = {asset_prices[i][0]: prices_array[i] for i in range(len(asset_prices))}

        return FinalPrices(prices=prices)
    except ContractLogicError as e:
        logger.error("OracleHelper contract call failed: %s", str(e))

        if config.ignore_empty_vault and total_assets == 0:
            logger.info(
                "Vault is empty and ignore_empty_vault is enabled, skipping OracleHelper call"
            )
            return FinalPrices(prices={asset: 0 for asset, _ in asset_prices})
        else:
            raise e


def get_oracle_helper_contract(config: OracleSettings) -> Contract:
    w3 = Web3(Web3.HTTPProvider(config.vault_rpc))
    abi = load_oracle_helper_abi()
    checksum_address = Web3.to_checksum_address(config.oracle_helper_address)
    return w3.eth.contract(address=checksum_address, abi=abi)


def encode_asset_prices(prices: PriceData) -> EncodedAssetPrices:
    """Encode asset prices for OracleHelper contract.

    Python's default string sort is case-sensitive and doesn't match Solidity's behavior.
    """
    asset_prices: list[tuple[str, int]] = []

    for address, price_per_base_unit in prices.prices.items():
        decimals = prices.decimals.get(address)
        if decimals is None:
            raise ValueError(f"Missing decimals for asset {address}")

        if address == prices.base_asset:
            normalized_price = 0
        else:
            integral_price = int(
                Decimal(price_per_base_unit).to_integral_value(rounding=ROUND_FLOOR)
            )
            normalized_price = integral_price * (10**decimals)

        asset_prices.append((address, normalized_price))

    asset_prices.sort(key=lambda item: int(item[0], 16))
    return EncodedAssetPrices(asset_prices=asset_prices)
