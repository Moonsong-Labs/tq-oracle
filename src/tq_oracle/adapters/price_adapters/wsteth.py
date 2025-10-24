from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from web3 import Web3

from ...abi import load_wsteth_abi
from ...constants import DEFAULT_MAINNET_RPC_URL, ETH_MAINNET_ASSETS
from ...settings import Network
from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...settings import OracleSettings

logger = logging.getLogger(__name__)


class WstETHAdapter(BasePriceAdapter):
    """Adapter for pricing ETH, WETH, and wstETH."""

    eth_address: str

    def __init__(self, config: OracleSettings):
        super().__init__(config)

        if config.network == Network.MAINNET:
            self.mainnet_rpc = config.l1_rpc
        else:
            # On L2s (Base, Sepolia, etc), use eth_mainnet_rpc or fall back to default
            self.mainnet_rpc = config.eth_mainnet_rpc or DEFAULT_MAINNET_RPC_URL
            if not config.eth_mainnet_rpc:
                logger.warning(
                    f"eth_mainnet_rpc not configured for {config.network.value}. "
                    f"Using default public RPC ({DEFAULT_MAINNET_RPC_URL}) for wstETH pricing. "
                    f"For production deployments, configure eth_mainnet_rpc in your settings."
                )

        assets = config.assets
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for WstETH adapter")
        self.eth_address = eth_address
        self.weth_address = assets["WETH"]
        self.wsteth_address = assets["WSTETH"]

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
        if prices_accumulator.base_asset != self.eth_address:
            raise ValueError("WstETH adapter only supports ETH as base asset")

        asset_addresses_lower = [addr.lower() for addr in asset_addresses]

        has_eth = self.eth_address.lower() in asset_addresses_lower
        has_weth = (
            self.weth_address is not None
            and self.weth_address.lower() in asset_addresses_lower
        )
        has_wsteth = (
            self.wsteth_address is not None
            and self.wsteth_address.lower() in asset_addresses_lower
        )

        if has_eth:
            prices_accumulator.prices[self.eth_address] = 1

        if has_weth:
            assert self.weth_address is not None
            prices_accumulator.prices[self.weth_address] = 10**18

        if has_wsteth:
            assert self.wsteth_address is not None
            wsteth_addr_actual = next(
                addr
                for addr in asset_addresses
                if addr.lower() == self.wsteth_address.lower()
            )

            w3 = Web3(Web3.HTTPProvider(self.mainnet_rpc))
            wsteth_abi = load_wsteth_abi()
            mainnet_wsteth = ETH_MAINNET_ASSETS["WSTETH"]
            assert mainnet_wsteth is not None
            wsteth_contract = w3.eth.contract(
                address=w3.to_checksum_address(mainnet_wsteth),
                abi=wsteth_abi,
            )

            wsteth_price = wsteth_contract.functions.getStETHByWstETH(10**18).call()
            prices_accumulator.prices[wsteth_addr_actual] = int(wsteth_price)

        self.validate_prices(prices_accumulator)

        return prices_accumulator
