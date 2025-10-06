"""Safe-related constants and network configurations."""

# Safe Transaction Service URLs by chain ID
SAFE_SERVICE_URLS = {
    1: "https://safe-transaction-mainnet.safe.global",
    11155111: "https://safe-transaction-sepolia.safe.global",
    100: "https://safe-transaction-gnosis-chain.safe.global",
    137: "https://safe-transaction-polygon.safe.global",
    42161: "https://safe-transaction-arbitrum.safe.global",
    10: "https://safe-transaction-optimism.safe.global",
}

# Network names for UI URL generation
NETWORK_PREFIXES = {
    1: "eth",
    11155111: "sep",
    100: "gno",
    137: "matic",
    42161: "arb1",
    10: "oeth",
}
