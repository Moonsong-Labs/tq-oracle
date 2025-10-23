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
# `tq-oracle.toml` Config file is automatically detected
uv run tq-oracle report

# Or specify config file explicitly
uv run tq-oracle report --config ./my-config.toml
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
| `--hyperliquid-env` | `HYPERLIQUID_ENV` | `hyperliquid_env` | `"mainnet"` | Hyperliquid environment (`"mainnet"` or `"testnet"`) |
| `--cctp-env` | `CCTP_ENV` | `cctp_env` | `"mainnet"` | CCTP environment (`"mainnet"` or `"testnet"`) |
| `--dry-run/--no-dry-run` | - | `dry_run` | `true` | Preview without sending transaction |
| `--private-key` | `PRIVATE_KEY` | ❌ *Never use TOML* | - | Private key for signing (required with Safe on --no-dry-run) |
| `--safe-key` | `SAFE_TRANSACTION_SERVICE_API_KEY` | ❌ *Never use TOML* | - | API key for Safe Transaction Service |
| `--ignore-empty-vault` | - | `ignore_empty_vault` | `false` | Suppress errors for empty vaults |
| `--ignore-timeout-check` | - | `ignore_timeout_check` | `false` | Allow forced submission bypassing timeout |
| `--ignore-active-proposal-check` | - | `ignore_active_proposal_check` | `false` | Allow duplicate submissions |
| `--pre-check-retries` | - | `pre_check_retries` | `3` | Number of pre-check retry attempts |
| `--pre-check-timeout` | - | `pre_check_timeout` | `12.0` | Timeout between pre-check retries (seconds) |
| - | - | `log_level` | `"INFO"` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| - | - | `chainlink_price_warning_tolerance_percentage` | `0.5` | Price deviation warning threshold (%) |
| - | - | `chainlink_price_failure_tolerance_percentage` | `1.0` | Price deviation failure threshold (%) |

#### TOML-Only Options (Not available via CLI)

| TOML Key | Default | Description |
|----------|---------|-------------|
| `max_calls` | `3` | Maximum number of RPC retry attempts |
| `rpc_max_concurrent_calls` | `5` | Maximum concurrent RPC connections |
| `rpc_delay` | `0.15` | Delay between RPC calls (seconds) |
| `rpc_jitter` | `0.10` | Random jitter for RPC delays (seconds) |

### Advanced Configuration: Subvault Adapters

TQ Oracle supports configuring multiple asset adapters per subvault address, allowing you to compose TVL from various sources (e.g., idle balances on L1 + portfolio on Hyperliquid).

**Configuration Structure:**

```toml
[[subvault_adapters]]
subvault_address = "0xb764428a29EAEbe8e2301F5924746F818b331F5A"
chain = "hyperliquid"                          # Chain: "l1" or "hyperliquid"
additional_adapters = ["hyperliquid", "idle_balances"]  # Asset adapters to run
skip_idle_balances = false                     # Skip default L1 idle_balances check
skip_subvault_existence_check = false          # Skip vault contract validation
```

**Available Asset Adapters:**
- `idle_balances` - Checks for idle USDC balances not yet deployed
- `hyperliquid` - Fetches portfolio value from Hyperliquid

**Example: Hyperliquid subvault with portfolio + idle USDC check**

```toml
[[subvault_adapters]]
subvault_address = "0xb764428a29EAEbe8e2301F5924746F818b331F5A"
chain = "hyperliquid"
additional_adapters = ["hyperliquid", "idle_balances"]
skip_idle_balances = false
skip_subvault_existence_check = false
```

See `tq-oracle-example.toml` for more configuration examples.

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
├── settings.py                       # Configuration management (pydantic-settings)
├── state.py                          # Application state container
├── pipeline/                         # Orchestration pipeline
├── domain/                           # Core domain models
├── adapters/                         # Protocol adapters
├── processors/                       # Data processing utilities
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

Asset adapters fetch asset holdings from specific protocols (e.g., Hyperliquid, Aave, Lido).

Quick overview:

1. **Create adapter file** in `src/tq_oracle/adapters/asset_adapters/` implementing `BaseAssetAdapter`
2. **Register adapter** in `src/tq_oracle/adapters/asset_adapters/__init__.py`'s `ADAPTER_REGISTRY`
3. **Write integration tests** in `tests/adapters/asset_adapters/`
4. **Add asset addresses** to `src/tq_oracle/constants.py` if needed

The adapter name in the registry is used in the `[[subvault_adapters]]` configuration's `additional_adapters` field.

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
    CowSwapAdapter,
    WstETHAdapter,
    MyOracleAdapter,  # Add your adapter here
]
```

> **Note:** `ChainlinkAdapter` is exported for use in price validators but not used directly in the main pricing pipeline.

### Price Validators

Price validators cross-check prices from the main price adapters against reference sources to detect anomalies or manipulation. They run after price fetching and can issue warnings or halt execution if prices deviate beyond configured thresholds.

1. **Create validator file** in `src/tq_oracle/adapters/price_validators/`:

```python
# src/tq_oracle/adapters/price_validators/my_validator.py
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BasePriceValidator, PriceValidationResult

if TYPE_CHECKING:
    from ...settings import OracleSettings

class MyValidator(BasePriceValidator):
    """Validator to cross-check prices against a reference oracle."""

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        # Initialize validator-specific connections

    @property
    def validator_name(self) -> str:
        return "my_validator"

    async def validate_prices(
        self,
        prices: dict[str, int]
    ) -> list[PriceValidationResult]:
        """Validate prices against reference oracle.

        Args:
            prices: Dict mapping asset addresses to prices (in wei, 18 decimals)

        Returns:
            List of validation results (warnings or failures)
        """
        # Implement validation logic
        results = []
        for asset_address, price in prices.items():
            reference_price = await self.fetch_reference_price(asset_address)
            deviation = abs(price - reference_price) / reference_price

            if deviation > 0.01:  # 1% deviation
                results.append(
                    PriceValidationResult(
                        asset_address=asset_address,
                        severity="warning",
                        message=f"Price deviation: {deviation:.2%}"
                    )
                )

        return results
```

2. **Register validator** in `src/tq_oracle/adapters/price_validators/__init__.py`:

```python
from .my_validator import MyValidator

PRICE_VALIDATORS = [
    ChainlinkValidator,
    MyValidator,  # Add your validator here
]
```

**Configuration:**

Price validators respect tolerance thresholds configured in `settings.py`:
- `chainlink_price_warning_tolerance_percentage` (default: 0.5%) - Issues warnings
- `chainlink_price_failure_tolerance_percentage` (default: 1.0%) - Halts execution

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
