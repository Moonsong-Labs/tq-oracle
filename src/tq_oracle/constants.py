"""Blockchain contract address constants."""

PRICE_FEED_USDC_ETH = "0x986b5E1e1755e3C2440e960477f25201B0a8bbD4"

USDC_MAINNET = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDC_SEPOLIA = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"

ETH_ASSET = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

HL_MAINNET_API_URL = "https://api.hyperliquid.xyz"
HL_TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"

HL_PROD_EVM_RPC = "https://rpc.hyperliquid.xyz/evm"
HL_TEST_EVM_RPC = "https://rpc.hyperliquid-testnet.xyz/evm"

DEFAULT_MAINNET_RPC_URL = "https://eth.drpc.org"
DEFAULT_SEPOLIA_RPC_URL = "https://sepolia.drpc.org"

MAINNET_ORACLE_HELPER = "0x000000005F543c38d5ea6D0bF10A50974Eb55E35"
SEPOLIA_ORACLE_HELPER = "0x65464fe20562C22B2802B4094d3E042E18b5dfC2"

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
