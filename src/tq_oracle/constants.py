"""Blockchain contract address constants."""

from typing import Optional, TypedDict


class NetworkAssets(TypedDict):
    USDC: Optional[str]
    USDT: Optional[str]
    USDS: Optional[str]
    ETH: Optional[str]
    WETH: Optional[str]
    WSTETH: Optional[str]


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
    "WSTETH": "0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452",
}

PRICE_FEED_USDC_ETH = "0x986b5E1e1755e3C2440e960477f25201B0a8bbD4"
PRICE_FEED_USDT_ETH = "0xEe9F2375b4bdF6387aa8265dD4FB8F16512A1d46"
PRICE_FEED_USDS_USD = "0xfF30586cD0F29eD462364C7e81375FC0C71219b1"
PRICE_FEED_ETH_USD = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"

USDC_HL_MAINNET = "0xb88339CB7199b77E23DB6E890353E22632Ba630f"
USDC_HL_TESTNET = "0x2B3370eE501B4a559b57D449569354196457D8Ab"

TOKEN_DECIMALS: dict[str, int] = {
    addr: decimals
    for addr, decimals in [
        (ETH_MAINNET_ASSETS.get("USDC"), 6),
        (SEPOLIA_ASSETS.get("USDC"), 6),
        (ETH_MAINNET_ASSETS.get("USDT"), 6),
        (ETH_MAINNET_ASSETS.get("USDS"), 18),
    ]
    if addr is not None
}

HL_MAINNET_API_URL = "https://api.hyperliquid.xyz"
HL_TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"

HL_PROD_EVM_RPC = "https://rpc.hyperliquid.xyz/evm"
HL_TEST_EVM_RPC = "https://rpc.hyperliquid-testnet.xyz/evm"

DEFAULT_MAINNET_RPC_URL = "https://eth.drpc.org"
DEFAULT_SEPOLIA_RPC_URL = "https://sepolia.drpc.org"
DEFAULT_BASE_RPC_URL = "https://mainnet.base.org"

MAINNET_ORACLE_HELPER = "0x000000005F543c38d5ea6D0bF10A50974Eb55E35"
SEPOLIA_ORACLE_HELPER = "0x65464fe20562C22B2802B4094d3E042E18b5dfC2"
BASE_ORACLE_HELPER = "0x9bB327889402AC19BF2D164eA79CcfE46c16a37B"


TOKEN_MESSENGER_V2_PROD = "0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d"
TOKEN_MESSENGER_V2_TEST = "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA"

CCTP_FINALITY_THRESHOLD_INSTANT = 1000  # ~8 seconds
CCTP_FINALITY_THRESHOLD_SLOW = 2000  # ~15 minutes

CCTP_LOOKBACK_BLOCKS = 80
CCTP_RATE_LIMITED_LOOKBACK_BLOCKS = 80  # 24 hours
RPC_RATE_LIMIT_DELAY = (
    5  # Delay in seconds between RPC calls to avoid rate limits with get_logs()
)
HL_BLOCK_TIME = 1  # Hyperliquid block time in seconds
L1_BLOCK_TIME = 12  # Ethereum L1 block time in seconds

# Retry Configuration for Post-Checks
MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 120  # 2 minutes


# Maximum allowed staleness (in seconds) for Hyperliquid portfolio values.
# Reject portfolio values older than this threshold.
HL_MAX_PORTFOLIO_STALENESS_SECONDS = 120  # 2 minutes
