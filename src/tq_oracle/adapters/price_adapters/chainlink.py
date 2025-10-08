from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import Web3

from ...abi import load_aggregator_abi
from ...constants import ETH_ASSET, USDC_MAINNET

from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class ChainlinkAdapter(BasePriceAdapter):
    """Adapter for querying Chainlink price feeds."""

    PRICE_FEED_USDC_ETH = "0x986b5E1e1755e3C2440e960477f25201B0a8bbD4"

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.l1_rpc = config.l1_rpc

    @property
    def adapter_name(self) -> str:
        return "chainlink"

    async def latest_price_and_decimals(self, feed_contract) -> tuple[int, int]:
        _, answer, _, _, _ = feed_contract.functions.latestRoundData().call()
        decimals = feed_contract.functions.decimals().call()
        return int(answer), int(decimals)

    def scale_to_18(self, value: int, decimals: int) -> int:
        if decimals == 18:
            return value
        if decimals < 18:
            return value * (10 ** (18 - decimals))
        return value // (10 ** (decimals - 18))

    async def fetch_prices(
        self, asset_addresses: list[str], price_data: PriceData
    ) -> PriceData:
        """Fetch asset prices from Chainlink price feeds.

        Args:
            asset_addresses: List of asset contract addresses to get prices for
            price_data: Price data to update

        Returns:
            Price data with updated prices
        """
        if price_data.base_asset != ETH_ASSET:
            raise ValueError("Chainlink adapter only supports ETH as base asset")

        if USDC_MAINNET not in asset_addresses:
            return price_data

        w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
        aggregator_abi = load_aggregator_abi()

        usdc_eth_feed = w3.eth.contract(
            address=w3.to_checksum_address(self.PRICE_FEED_USDC_ETH),
            abi=aggregator_abi,
        )

        usdc_eth_answer, usdc_eth_decimals = await self.latest_price_and_decimals(
            usdc_eth_feed
        )

        usdc_eth_scaled = self.scale_to_18(usdc_eth_answer, usdc_eth_decimals)

        price_data.prices[USDC_MAINNET] = usdc_eth_scaled

        return price_data
