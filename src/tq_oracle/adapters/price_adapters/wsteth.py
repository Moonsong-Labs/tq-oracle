from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import Web3

from ...abi import load_wsteth_abi
from ...constants import ETH_ASSET, WETH_MAINNET, WSTETH_MAINNET
from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class WstETHAdapter(BasePriceAdapter):
    """Adapter for pricing ETH, WETH, and wstETH."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.l1_rpc = config.l1_rpc
        self.weth_address = WETH_MAINNET
        self.wsteth_address = WSTETH_MAINNET

    @property
    def adapter_name(self) -> str:
        return "wsteth"

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices for ETH, WETH, and wstETH.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                have base_asset set to ETH (wei). All prices are 18-decimal values
                representing wei per 1 unit of the asset.

        Returns:
            The same accumulator with prices merged in.

        Notes:
            - Only ETH as base asset is supported.
            - ETH is the base asset and is set to 1.
            - WETH is 1:1 with ETH (10**18).
            - wstETH price is derived from the wstETH contract's getStETHByWstETH function.
        """
        if prices_accumulator.base_asset != ETH_ASSET:
            raise ValueError("WstETH adapter only supports ETH as base asset")

        has_eth = ETH_ASSET in asset_addresses
        has_weth = self.weth_address in asset_addresses
        has_wsteth = self.wsteth_address in asset_addresses

        if has_eth:
            prices_accumulator.prices[ETH_ASSET] = 1

        if has_weth:
            prices_accumulator.prices[self.weth_address] = 10**18

        if has_wsteth:
            w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
            wsteth_abi = load_wsteth_abi()
            wsteth_contract = w3.eth.contract(
                address=w3.to_checksum_address(self.wsteth_address),
                abi=wsteth_abi,
            )

            wsteth_price = wsteth_contract.functions.getStETHByWstETH(10**18).call()
            prices_accumulator.prices[self.wsteth_address] = int(wsteth_price)

        await self.validate_prices(prices_accumulator)

        return prices_accumulator
