from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import backoff
import requests

from ...constants import TOKEN_DECIMALS
from ...settings import Network
from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...settings import OracleSettings


class CowSwapAdapter(BasePriceAdapter):
    """Adapter for querying CoW Protocol native prices."""

    eth_address: str

    NETWORK_API_URLS: dict[Network, str] = {
        Network.MAINNET: "https://api.cow.fi/mainnet/api/v1",
        Network.SEPOLIA: "https://api.cow.fi/sepolia/api/v1",
        Network.BASE: "https://api.cow.fi/base/api/v1",
    }

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.api_base_url = self.NETWORK_API_URLS[config.network]
        assets = config.assets
        eth_address = assets["ETH"]
        if eth_address is None:
            raise ValueError("ETH address is required for CowSwap adapter")
        self.eth_address = eth_address
        self.usdc_address = assets["USDC"]
        self.usdt_address = assets["USDT"]
        self.usds_address = assets["USDS"]

    @property
    def adapter_name(self) -> str:
        return "cow_swap"

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
            - Supports USDC, USDT, and USDS.
            - CoW API returns price per 1 whole token in ETH.
        """
        if prices_accumulator.base_asset != self.eth_address:
            raise ValueError("CowSwap adapter only supports ETH as base asset")

        supported_assets = {
            self.usdc_address,
            self.usdt_address,
            self.usds_address,
        }

        supported_assets = [asset for asset in supported_assets if asset is not None]

        for asset_address in asset_addresses:
            if asset_address not in supported_assets:
                continue

            token_decimals = TOKEN_DECIMALS.get(asset_address)
            if token_decimals is None:
                continue

            native_price = await self.fetch_native_price(asset_address)
            price_wei = int(native_price * 10**18)
            price_wei_normalized = price_wei // (10 ** (18 - token_decimals))
            prices_accumulator.prices[asset_address] = price_wei_normalized

        self.validate_prices(prices_accumulator)

        return prices_accumulator
