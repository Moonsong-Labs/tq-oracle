# TQ Oracle - TVL Reporting CLI

A command-line application for collecting Total Value Locked (TVL) data from vault protocols using modular protocol adapters.

## Overview

TQ Oracle performs read smart contract READ calls through a registry of protocol adapters to aggregate TVL data for specified vaults. Each adapter is responsible for querying specific contracts and returning standardized asset price data.

## Running without installing

You can run this CLI without any git cloning, directly with `uv`

```sh
uvx --from git+https://github.com/Moonsong-Labs/tq-oracle.git tq-oracle --help   
```

## Installation

This project uses `uv` for dependency management:

```bash
# Clone the repository
git clone <repo-url>
cd tq-oracle

# Install dependencies
uv sync

```

## Usage

### Configuration Methods

TQ Oracle supports three ways to configure the application, with the following precedence (highest to lowest):

1. **CLI Arguments** - Explicit command-line flags
2. **Environment Variables** - Set via shell or `.env` file
3. **TOML Configuration File** - Persistent configuration

### Basic Command

```bash
uv run tq-oracle 0x277C6A642564A91ff78b008022D65683cEE5CCC5 --dry-run
```

### Using a Configuration File (Recommended)

Create a `tq-oracle.toml` file in your project directory or `~/.config/tq-oracle/config.toml`:

```toml
vault_address = "0x277C6A642564A91ff78b008022D65683cEE5CCC5"
testnet = false

l1_rpc = "https://ethereum-rpc.publicnode.com"
hl_rpc = "https://api.hyperliquid.xyz/evm"

dry_run = true

ignore_empty_vault = false
pre_check_retries = 3
pre_check_timeout = 12.0
```

Then run with minimal arguments:

```bash
# Config file is automatically detected
uv run tq-oracle

# Or specify config file explicitly
uv run tq-oracle --config ./my-config.toml
```

See `tq-oracle.toml.example` for a complete configuration template with all available options.

### With Environment Variables

Create a `.env` file:

```env
L1_RPC=https://sepolia.drpc.org
HL_SUBVAULT_ADDRESS=0xYourHyperliquidSubvaultAddress
PRIVATE_KEY=0xYourPrivateKey
```

Then run:

```bash
uv run tq-oracle <VAULT_ADDRESS> [OPTIONS]
```

> [!IMPORTANT]  
> Always use environment variables or CLI flags for secrets (private keys, API keys). Never store them in TOML configuration files.

#### Example

```bash
uv run tq-oracle 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --dry-run \
  --ignore-empty-vault \
  --hl-subvault-address 0xb764428a29EAEbe8e2301F5924746F818b331F5A
```

### Configuration Options

All configuration options can be set via CLI arguments, environment variables, or TOML config file.

| CLI Option | Environment Variable | TOML Key | Default | Description |
|------------|---------------------|-----------|---------|-------------|
| `VAULT_ADDRESS` | - | `vault_address` | *required* | Vault contract address (positional argument) |
| `--config` `-c` | - | - | Auto-detect | Path to TOML configuration file |
| `--oracle-helper-address` `-h` | - | `oracle_helper_address` | Auto (mainnet/testnet) | OracleHelper contract address |
| `--l1-rpc` | `L1_RPC` | `l1_rpc` | Auto (mainnet/testnet) | Ethereum L1 RPC endpoint |
| `--hl-rpc` | `HL_EVM_RPC` | `hl_rpc` | Auto (mainnet/testnet) | Hyperliquid RPC endpoint |
| `--l1-subvault-address` | `L1_SUBVAULT_ADDRESS` | `l1_subvault_address` | - | L1 subvault for CCTP monitoring |
| `--hl-subvault-address` | `HL_SUBVAULT_ADDRESS` | `hl_subvault_address` | Vault address | Hyperliquid subvault address |
| `--safe-address` `-s` | - | `safe_address` | - | Gnosis Safe address for multi-sig |
| `--testnet/--no-testnet` | - | `testnet` | `false` | Use testnet instead of mainnet |
| `--dry-run/--no-dry-run` | - | `dry_run` | `true` | Preview without sending transaction |
| `--private-key` | `PRIVATE_KEY` | ❌ *Never use TOML* | - | Private key for signing (required with Safe on --no-dry-run) |
| `--safe-key` | `SAFE_TRANSACTION_SERVICE_API_KEY` | ❌ *Never use TOML* | - | API key for Safe Transaction Service |
| `--ignore-empty-vault` | - | `ignore_empty_vault` | `false` | Suppress errors for empty vaults |
| `--ignore-timeout-check` | - | `ignore_timeout_check` | `false` | Allow forced submission bypassing timeout |
| `--ignore-active-proposal-check` | - | `ignore_active_proposal_check` | `false` | Allow duplicate submissions |
| `--pre-check-retries` | - | `pre_check_retries` | `3` | Number of pre-check retry attempts |
| `--pre-check-timeout` | - | `pre_check_timeout` | `12.0` | Timeout between pre-check retries (seconds) |

#### TOML-Only Options (Not available via CLI)

| TOML Key | Default | Description |
|----------|---------|-------------|
| `max_calls` | `3` | Maximum number of RPC retry attempts |
| `rpc_max_concurrent_calls` | `5` | Maximum concurrent RPC connections |
| `rpc_delay` | `0.15` | Delay between RPC calls (seconds) |
| `rpc_jitter` | `0.10` | Random jitter for RPC delays (seconds) |

### Examples

> [!IMPORTANT]  
> Until Mellow has deployments of the vaults available for testing, you may need to use `--ignore-empty-vault` flag to overcome empty-asset errors.

**Dry-run on mainnet:**

```bash
uv run tq-oracle 0x277C6A642564A91ff78b008022D65683cEE5CCC5 --dry-run
```

**Dry-run with custom Hyperliquid subvault:**

```bash
uv run tq-oracle 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --hl-subvault-address 0xYourHyperliquidAddress
```

**Execute on testnet with Safe:**

```bash
uv run tq-oracle 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --safe-address 0xabc... \
  --testnet \
  --no-dry-run \
  --private-key 0x...
```

**Testing empty vault (pre-deployment):**

```bash
uv run tq-oracle 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --ignore-empty-vault
```

## Architecture

```sh
src/tq_oracle/
├── main.py                           # CLI entry point (Typer)
├── config.py                         # Configuration dataclass
├── orchestrator.py                   # Main control flow orchestration
├── adapters/                         # Protocol adapters (asset/price/check)
├── processors/                       # Data processing pipeline
├── report/                           # Report generation and publishing
├── safe/                             # Safe transaction building
├── checks/                           # Pre-flight validation orchestration
└── abis/                             # Contract ABIs (JSON)
```

## Pre-Flight Checks

Before processing TVL data, TQ Oracle runs automated pre-flight validation checks to ensure data integrity:

- **Safe State Validation**: Ensures no duplicate or pending reports exist
- **CCTP Bridge Detection**: Identifies in-flight USDC transfers between L1 and Hyperliquid
- **Check Retry Logic**: Automatically retries failed checks with exponential backoff when recommended

These checks prevent race conditions and ensure accurate TVL snapshots by detecting ongoing cross-chain transfers that could affect asset balances.

### Testing CCTP Bridge Detection

A standalone test script is available to verify CCTP bridge in-flight detection:

```bash
# Test on mainnet
uv run python scripts/check_cctp_inflight.py \
  0xL1SubvaultAddress \
  0xHLSubvaultAddress
```

## Adding New Adapters

### Asset Adapters

Asset adapters fetch asset holdings from specific protocols (e.g., Hyperliquid, Aave, Uniswap).

1. **Create adapter file** in `src/tq_oracle/adapters/asset_adapters/`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AssetData, BaseAssetAdapter

if TYPE_CHECKING:
    from ...config import OracleCLIConfig

class MyProtocolAdapter(BaseAssetAdapter):
    """Adapter for querying MyProtocol assets."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        # Initialize any protocol-specific clients/connections

    @property
    def adapter_name(self) -> str:
        return "my_protocol"

    async def fetch_assets(self, vault_address: str) -> list[AssetData]:
        """Fetch asset data from MyProtocol for the given vault."""
        # Implement your protocol-specific logic here
        return [
            AssetData(asset_address="0x...", amount=1000000),
        ]
```

2. **Register adapter** in `src/tq_oracle/adapters/asset_adapters/__init__.py`:

```python
from .my_protocol import MyProtocolAdapter

ASSET_ADAPTERS = [
    HyperliquidAdapter,
    MyProtocolAdapter,  # Add your adapter here
]
```

### Price Adapters

Price adapters fetch USD prices for assets from price oracles (e.g., Chainlink, Pyth).

1. **Create adapter file** in `src/tq_oracle/adapters/price_adapters/`:

```python
# src/tq_oracle/adapters/price_adapters/my_oracle.py
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BasePriceAdapter, PriceData

if TYPE_CHECKING:
    from ...config import OracleCLIConfig

class MyOracleAdapter(BasePriceAdapter):
    """Adapter for querying MyOracle price feeds."""

    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        # Initialize oracle connections

    @property
    def adapter_name(self) -> str:
        return "my_oracle"

    async def fetch_prices(self, asset_addresses: list[str]) -> list[PriceData]:
        """Fetch USD prices for the given asset addresses."""
        # Implement price fetching logic
        return [
            PriceData(asset_address=addr, price_usd=1000000000000000000)
            for addr in asset_addresses
        ]
```

2. **Register adapter** in `src/tq_oracle/adapters/price_adapters/__init__.py`:

```python
from .my_oracle import MyOracleAdapter

PRICE_ADAPTERS = [
    ChainlinkAdapter,
    MyOracleAdapter,  # Add your adapter here
]
```

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
pytest

# Lint code
ruff check src/

# Format code
ruff format src/
```

---

## External Links

- `flexible-vaults` [repo](https://github.com/mellow-finance/flexible-vaults)
- Hyperliquid API [documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- `cctp-v2` [contracts](https://github.com/circlefin/evm-cctp-contracts/tree/master/src/v2)
- DeBridge [contracts](https://github.com/debridge-finance/dln-contracts/tree/main/contracts/DLN)
