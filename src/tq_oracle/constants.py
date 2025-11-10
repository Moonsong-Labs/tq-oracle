"""Blockchain contract address constants."""

from typing import Optional, TypedDict


class NetworkAssets(TypedDict):
    USDC: Optional[str]
    USDT: Optional[str]
    USDS: Optional[str]
    ETH: Optional[str]
    WETH: Optional[str]
    WSTETH: Optional[str]


class StakewiseAddresses(TypedDict):
    """Hard-coded StakeWise contract addresses per network."""

    os_token: str
    os_token_vault_escrow: str
    vault: str


ETH_ASSET = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

ETH_MAINNET_ASSETS: NetworkAssets = {
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "USDS": "0xdC035D45d973E3EC169d2276DDab16f1e407384F",
    "ETH": ETH_ASSET,
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "WSTETH": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
}

SEPOLIA_ASSETS: NetworkAssets = {
    "USDC": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
    "USDT": None,
    "USDS": None,
    "ETH": ETH_ASSET,
    "WETH": "0xf531B8F309Be94191af87605CfBf600D71C2cFe0",
    "WSTETH": None,
}

BASE_ASSETS: NetworkAssets = {
    "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "USDT": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
    "USDS": "0x820c137fa70c8691f0e44dc420a5e53c168921dc",
    "ETH": ETH_ASSET,
    "WETH": "0x4200000000000000000000000000000000000006",
    "WSTETH": "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452",
}

# Hardcoded overrides, if required
# https://docs.pyth.network/price-feeds/core/price-feeds/price-feed-ids
PYTH_PRICE_FEED_IDS: dict[str, str] = {}

DEFAULT_MAINNET_RPC_URL = "https://eth.drpc.org"
DEFAULT_SEPOLIA_RPC_URL = "https://sepolia.drpc.org"
DEFAULT_BASE_RPC_URL = "https://mainnet.base.org"

MAINNET_ORACLE_HELPER = "0x000000005F543c38d5ea6D0bF10A50974Eb55E35"
SEPOLIA_ORACLE_HELPER = "0x65464fe20562C22B2802B4094d3E042E18b5dfC2"
BASE_ORACLE_HELPER = "0x9bB327889402AC19BF2D164eA79CcfE46c16a37B"

STAKEWISE_MAINNET_ADDRESSES: StakewiseAddresses = {
    "os_token": "0xf1C9acDc66974dFB6dEcB12aA385b9cD01190E38",
    "os_token_vault_escrow": "0x09e84205DF7c68907e619D07aFD90143c5763605",
    "vault": "0xe6D8d8Ac54461b1c5ed15740eeE322043F696C08",
}

STAKEWISE_ADDRESSES: dict[str, StakewiseAddresses] = {
    "mainnet": STAKEWISE_MAINNET_ADDRESSES,
}


STAKEWISE_EXIT_LOG_CHUNK = 1_000
STAKEWISE_EXIT_MAX_LOOKBACK_BLOCKS = 28_800  # ~4 days on 12s blocks

TOKEN_MESSENGER_V2_PROD = "0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d"
TOKEN_MESSENGER_V2_TEST = "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA"

RPC_RATE_LIMIT_DELAY = (
    5  # Delay in seconds between RPC calls to avoid rate limits with get_logs()
)
L1_BLOCK_TIME = 12  # Ethereum L1 block time in seconds

# Retry Configuration for Post-Checks
MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 120  # 2 minutes
