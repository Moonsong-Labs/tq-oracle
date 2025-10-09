from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import Web3

from ...abi import load_aggregator_abi
from ...constants import ETH_ASSET, USDC_MAINNET, PRICE_FEED_USDC_ETH, USDC_SEPOLIA
from ...units import scale_to_18

from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig


class ChainlinkAdapter(BasePriceAdapter):
    """Adapter for querying Chainlink price feeds."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.l1_rpc = config.l1_rpc
        self.usdc_address = USDC_SEPOLIA if config.testnet else USDC_MAINNET

    @property
    def adapter_name(self) -> str:
        return "chainlink"

    async def latest_price_and_decimals(self, feed_contract) -> tuple[int, int]:
        _, answer, _, _, _ = feed_contract.functions.latestRoundData().call()
        decimals = feed_contract.functions.decimals().call()
        return int(answer), int(decimals)

    async def fetch_prices(
        self, asset_addresses: list[str], prices_accumulator: PriceData
    ) -> PriceData:
        """Fetch and accumulate asset prices from Chainlink price feeds.

        Args:
            asset_addresses: List of asset contract addresses to get prices for.
            prices_accumulator: Existing price accumulator to update. Must
                have base_asset set to ETH (wei). All prices are 18-decimal values
                representing wei per 1 unit of the asset.

        Returns:
            The same accumulator with Chainlink-derived prices merged in.

        Notes:
            - Only ETH as base asset is supported.
        """
        if prices_accumulator.base_asset != ETH_ASSET:
            raise ValueError("Chainlink adapter only supports ETH as base asset")

        if self.usdc_address not in asset_addresses:
            return prices_accumulator

        w3 = Web3(Web3.HTTPProvider(self.l1_rpc))
        aggregator_abi = load_aggregator_abi()

        usdc_eth_feed = w3.eth.contract(
            address=w3.to_checksum_address(PRICE_FEED_USDC_ETH),
            abi=aggregator_abi,
        )

        usdc_eth_answer, usdc_eth_decimals = await self.latest_price_and_decimals(
            usdc_eth_feed
        )

        usdc_eth_scaled = scale_to_18(usdc_eth_answer, usdc_eth_decimals)

        prices_accumulator.prices[self.usdc_address] = usdc_eth_scaled

        return prices_accumulator
