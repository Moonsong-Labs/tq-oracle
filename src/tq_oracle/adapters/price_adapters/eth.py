from __future__ import annotations

import logging
from decimal import Decimal

from eth_typing import URI
from web3 import Web3

from ...abi import load_ostoken_vault_controller_abi
from ...constants import STAKEWISE_ADDRESSES
from ...settings import Network, OracleSettings
from .base import BasePriceAdapter, PriceData
from typing import cast

logger = logging.getLogger(__name__)


class ETHAdapter(BasePriceAdapter):
    """Adapter for pricing ETH, WETH, and osETH."""

    eth_address: str

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        assets = config.assets
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for ETH adapter")
        self.eth_address = eth_address
        self.weth_address = assets["WETH"]

        self._oseth_address = (
            config.assets.get("OSETH")
            if (config.additional_asset_support and config.network == Network.MAINNET)
            else None
        )
        self._rpc_url = config.vault_rpc_required
        self._block_number = config.block_number_required
        self.w3 = (
            Web3(Web3.HTTPProvider(URI(self._rpc_url))) if self._oseth_address else None
        )

    @property
    def adapter_name(self) -> str:
        return "eth"

    def _get_oseth_price(self) -> int:
        """Get osETH price in ETH by calling convertToAssets(1e18) on the controller.

        Returns:
            Price in wei (18 decimals) representing ETH per 1 osETH.
        """
        defaults = STAKEWISE_ADDRESSES[self.config.network.value]
        oseth_controller_address = defaults["os_token_vault_controller"]
        w3 = cast(Web3, self.w3)
        controller = w3.eth.contract(
            address=w3.to_checksum_address(oseth_controller_address),
            abi=load_ostoken_vault_controller_abi(),
        )

        # Get price for 1 osETH (1e18 shares)
        price = controller.functions.convertToAssets(10**18).call(
            block_identifier=self._block_number
        )
        return int(price)

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices for ETH, WETH, and osETH.

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
            - osETH price is fetched from OsTokenVaultController.convertToAssets().
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
        has_oseth = (
            self._oseth_address is not None
            and self._oseth_address.lower() in asset_addresses_lower
        )

        if has_eth:
            prices_accumulator.prices[self.eth_address] = Decimal(1.0)
            prices_accumulator.decimals.setdefault(self.eth_address, 18)

        if has_weth:
            assert self.weth_address is not None
            prices_accumulator.prices[self.weth_address] = Decimal(1.0)
            prices_accumulator.decimals.setdefault(self.weth_address, 18)

        if has_oseth:
            assert self._oseth_address is not None
            oseth_price = self._get_oseth_price()
            # Convert wei price to Decimal ratio (price / 1e18)
            prices_accumulator.prices[self._oseth_address] = Decimal(oseth_price) / Decimal(10**18)
            prices_accumulator.decimals.setdefault(self._oseth_address, 18)
            logger.debug("osETH price: %d wei per osETH", oseth_price)

        return prices_accumulator
