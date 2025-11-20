from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, ROUND_HALF_UP

import backoff
import requests
from web3 import Web3

from ...abi import load_erc20_abi
from ...settings import Network, OracleSettings
from .base import BasePriceAdapter, PriceData

logger = logging.getLogger(__name__)


class CowSwapAdapter(BasePriceAdapter):
    """Adapter for querying CoW Protocol native prices.

    This adapter fetches prices for all assets EXCEPT those handled by specialized adapters.
    Assets on the list (ETH, WETH) are skipped as they're handled by ETHAdapter.
    """

    eth_address: str

    NETWORK_API_URLS: dict[Network, str] = {
        Network.MAINNET: "https://api.cow.fi/mainnet/api/v1",
        Network.SEPOLIA: "https://api.cow.fi/sepolia/api/v1",
        Network.BASE: "https://api.cow.fi/base/api/v1",
    }

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.api_base_url = self.NETWORK_API_URLS[config.network]
        self.vault_rpc = config.vault_rpc
        self.block_number = config.block_number_required
        assets = config.assets
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for CowSwap adapter")
        self.eth_address = eth_address

        self._decimals_cache: dict[str, int] = {}

        self.skipped_assets = {
            addr.lower()
            for addr in [
                assets["ETH"],
                assets["WETH"],
            ]
            if addr is not None
        }

    @property
    def adapter_name(self) -> str:
        return "cow_swap"

    async def get_token_decimals(self, token_address: str) -> int:
        """Fetch token decimals from on-chain contract, with caching.

        Args:
            token_address: The token contract address

        Returns:
            Number of decimals for the token
        """
        if token_address in self._decimals_cache:
            return self._decimals_cache[token_address]

        w3 = Web3(Web3.HTTPProvider(self.vault_rpc))
        erc20_abi = load_erc20_abi()
        token_contract = w3.eth.contract(
            address=w3.to_checksum_address(token_address),
            abi=erc20_abi,
        )

        decimals = await asyncio.to_thread(
            lambda: int(
                token_contract.functions.decimals().call(
                    block_identifier=self.block_number
                )
            )
        )

        self._decimals_cache[token_address] = decimals
        logger.debug(f" Fetched decimals for {token_address}: {decimals}")

        return decimals

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.RequestException, requests.exceptions.HTTPError),
        max_time=5,
        giveup=lambda e: isinstance(e, requests.exceptions.HTTPError)
        and e.response is not None
        and e.response.status_code != 429,
        jitter=backoff.full_jitter,
    )
    async def fetch_native_price(self, token_address: str) -> float:
        """Fetch native price (ETH) for a token from CoW Protocol API.

        Args:
            token_address: The token contract address

        Returns:
            Native price in ETH
        """
        url = f"{self.api_base_url}/token/{token_address}/native_price"
        logger.debug(f"Calling {url}")
        response = await asyncio.to_thread(requests.get, url)
        response.raise_for_status()
        data = response.json()
        return float(data["price"])

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices from CoW Swap API.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                have base_asset set to ETH (wei). All prices are 18-decimal values
                representing wei per 1 unit of the asset.

        Returns:
            The same accumulator with CoW Swap-derived prices merged in.

        Notes:
            - Only ETH as base asset is supported.
            - Fetches native prices directly from CoW Swap API.
            - Processes all assets EXCEPT those on the skipped_assets (ETH, WETH).
            - Token decimals are fetched dynamically from on-chain and cached.
            - CoW API returns the amount of native token atoms (wei) needed per
              single smallest token unit (base unit).
        """
        if prices_accumulator.base_asset != self.eth_address:
            raise ValueError("CowSwap adapter only supports ETH as base asset")

        for asset_address in asset_addresses:
            if asset_address.lower() in self.skipped_assets:
                logger.debug(f" Skipping asset: {asset_address}")
                continue

            try:
                token_decimals = await self.get_token_decimals(asset_address)
                native_price = await self.fetch_native_price(asset_address)

                price_wei = int(
                    Decimal(str(native_price))
                    .scaleb(18)
                    .to_integral_value(rounding=ROUND_HALF_UP)
                )
                logger.debug(
                    f" Fetched price for {asset_address}: {price_wei} (D18) per base unit (decimals: {token_decimals})"
                )
                prices_accumulator.prices[asset_address] = price_wei

            except Exception as e:
                logger.warning(f" Failed to fetch price for {asset_address}: {e}")
                continue

        self.validate_prices(prices_accumulator)

        return prices_accumulator
