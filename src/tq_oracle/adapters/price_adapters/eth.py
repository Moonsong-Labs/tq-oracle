from __future__ import annotations

import logging

from ...settings import OracleSettings
from .base import BasePriceAdapter, PriceData

logger = logging.getLogger(__name__)


class ETHAdapter(BasePriceAdapter):
    """Adapter for pricing ETH and WETH."""

    eth_address: str

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        assets = config.assets
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for ETH adapter")
        self.eth_address = eth_address
        self.weth_address = assets["WETH"]

    @property
    def adapter_name(self) -> str:
        return "eth"

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices for ETH and WETH.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                have base_asset set to ETH (wei). All prices are 18-decimal values
                representing wei per 1 unit of the asset.

        Returns:
            The same accumulator with prices merged in.

        Notes:
            - Only ETH as base asset is supported.
            - ETH is priced at 10**18 (1:1 ratio in 18-decimal format).
            - WETH is 1:1 with ETH (10**18).
            - The base asset price is set to 0 by encode_asset_prices() before sending to OracleHelper.
        """
        if prices_accumulator.base_asset != self.eth_address:
            raise ValueError("ETH adapter only supports ETH as base asset")

        asset_addresses_lower = [addr.lower() for addr in asset_addresses]

        has_eth = self.eth_address.lower() in asset_addresses_lower
        has_weth = (
            self.weth_address is not None
            and self.weth_address.lower() in asset_addresses_lower
        )

        if has_eth:
            prices_accumulator.prices[self.eth_address] = 10**18

        if has_weth:
            assert self.weth_address is not None
            prices_accumulator.prices[self.weth_address] = 10**18

        self.validate_prices(prices_accumulator)

        return prices_accumulator
