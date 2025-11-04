# TQ Oracle - TVL Reporting CLI

A command-line application for collecting Total Value Locked (TVL) data from vault protocols using modular protocol adapters.

## Overview

TQ Oracle performs read smart contract READ calls through a registry of protocol adapters to aggregate TVL data for specified vaults. Each adapter is responsible for querying specific contracts and returning standardized asset price data.

For detailed system architecture and integration with Mellow Finance flexible-vaults, see [ARCHITECTURE.md](ARCHITECTURE.md).

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

Run the CLI with a vault address and dry-run flag to preview reports without submission.

### Using a Configuration File (Recommended)

- Create `tq-oracle.toml` in project directory or `~/.config/tq-oracle/config.toml`
- Configure vault address, network, RPC endpoints, and operational settings
- Run with minimal CLI arguments - config file is auto-detected
- See `tq-oracle.toml.example` for complete configuration template

### With Environment Variables

- Create `.env` file for environment-specific settings
- Set RPC endpoints, subvault addresses, and other non-secret configuration
- **Important**: Always use environment variables or CLI flags for secrets (private keys, API keys) - never store them in TOML files
- Run with vault address and any additional CLI options

### Configuration Options

All configuration options can be set via CLI arguments, environment variables, or TOML config file.

| CLI Option | Environment Variable | TOML Key | Default | Description |
|------------|---------------------|-----------|---------|-------------|
| `VAULT_ADDRESS` | - | `vault_address` | *required* | Vault contract address (positional argument) |
| `--config` `-c` | - | - | Auto-detect | Path to TOML configuration file |
| `--oracle-helper-address` `-h` | - | `oracle_helper_address` | Auto (mainnet/testnet) | OracleHelper contract address |
| `--vault-rpc` | `VAULT_RPC` | `vault_rpc` | Auto (mainnet/sepolia/base) | Vault network RPC endpoint |
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

TQ Oracle supports configuring multiple asset adapters per subvault address, allowing you to compose TVL from various sources.

**Configuration via TOML:**

- Specify target subvault address
- Define which chain the subvault operates on (L1 or Hyperliquid)
- List additional adapters to run for this subvault
- Option to skip default idle balances check
- Option to skip subvault existence validation

**Available Asset Adapters:**

- `idle_balances` - Checks for idle USDC balances not yet deployed
- `hyperliquid` - Fetches portfolio value from Hyperliquid

See `tq-oracle-example.toml` for complete configuration examples.

### Usage Examples

**Run with auto-detected config file:**

```bash
# Loads from tq-oracle.toml or ~/.config/tq-oracle/config.toml
tq-oracle
```

**Run with explicit vault address:**

```bash
# Override vault address from config
tq-oracle 0xYourVaultAddress
```

**Run with custom config file:**

```bash
tq-oracle --config path/to/custom-config.toml
```

**Run with network override:**

```bash
tq-oracle --network sepolia 0xYourVaultAddress
```

**Preview configuration without running:**

```bash
tq-oracle --show-config
```

**Common Usage Patterns:**

- **Dry-run on mainnet**: Preview report generation without submitting to chain
- **Custom subvault**: Specify Hyperliquid subvault address for cross-chain asset tracking
- **Testnet execution**: Run against testnet with Safe multi-sig for testing
- **Pre-deployment testing**: Test with empty vaults using ignore flags

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

A standalone test script is available in `scripts/check_cctp_inflight.py` to verify CCTP bridge in-flight detection with L1 and Hyperliquid subvault addresses.

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

1. **Create adapter file** in `src/tq_oracle/adapters/price_adapters/` implementing `BasePriceAdapter`
2. **Register adapter** in `src/tq_oracle/adapters/price_adapters/__init__.py`'s `PRICE_ADAPTERS` list
3. **Implement async `fetch_prices()` method** to query oracle and return price data
4. **Write unit tests** in `tests/adapters/price_adapters/`

> **Note:** `ChainlinkAdapter` is exported for use in price validators but not used directly in the main pricing pipeline.

### Price Validators

Price validators cross-check prices from the main price adapters against reference sources to detect anomalies or manipulation. They run after price fetching and can issue warnings or halt execution if prices deviate beyond configured thresholds.

1. **Create validator file** in `src/tq_oracle/adapters/price_validators/` implementing `BasePriceValidator`
2. **Register validator** in `src/tq_oracle/adapters/price_validators/__init__.py`'s `PRICE_VALIDATORS` list
3. **Implement async `validate_prices()` method** to cross-check prices and return validation results
4. **Configure tolerance thresholds** in settings for warning and failure levels
5. **Write unit tests** in `tests/adapters/price_validators/`

Validators respect tolerance thresholds configured in `settings.py`:
- `chainlink_price_warning_tolerance_percentage` (default: 0.5%) - Issues warnings
- `chainlink_price_failure_tolerance_percentage` (default: 1.0%) - Halts execution

## Development

- **Install dependencies**: Use `uv sync --all-extras` for development dependencies
- **Run tests**: Execute test suite with pytest
- **Lint code**: Check code quality with ruff
- **Format code**: Apply consistent formatting with ruff format

---

## External Links

- `flexible-vaults` [repo](https://github.com/mellow-finance/flexible-vaults)
- Hyperliquid API [documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- `cctp-v2` [contracts](https://github.com/circlefin/evm-cctp-contracts/tree/master/src/v2)
- DeBridge [contracts](https://github.com/debridge-finance/dln-contracts/tree/main/contracts/DLN)
