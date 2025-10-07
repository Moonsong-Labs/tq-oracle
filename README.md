# TQ Oracle - TVL Reporting CLI

A command-line application for collecting Total Value Locked (TVL) data from vault protocols using modular protocol adapters.

## Overview

TQ Oracle performs read smart contract READ calls through a registry of protocol adapters to aggregate TVL data for specified vaults. Each adapter is responsible for querying specific contracts and returning standardized asset price data.

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

> [!IMPORTANT]
> The following is **INTENDED** function surface but not actually in place yet.

### Basic Command

```bash
uv run tq-oracle \
  --vault-address 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --destination 0xYourDestinationAddress \
  --l1-rpc https://eth.drpc.org \
  --hl-rpc https://your-hyperliquid-rpc \
  --dry-run
```

### With Environment Variables

Create a `.env` file:

```env
L1_RPC_URL=https://eth.drpc.org
HL_RPC_URL=https://your-hyperliquid-rpc
PRIVATE_KEY=0xYourPrivateKey
```

Then run:

```bash
uv run tq-oracle --vault-address 0xb764428a29EAEbe8e2301F5924746F818b331F5A \
    --oracle-address 0xb764428a29EAEbe8e2301F5924746F818b331F5A \
    --testnet
```

### CLI Options

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `--vault-address` | - | *required* | Vault contract address to query |
| `--destination` | - | *required* | Destination EOA for transaction |
| `--l1-rpc` | `L1_RPC_URL` | `https://eth.drpc.org` | Ethereum mainnet RPC endpoint |
| `--hl-rpc` | `HL_RPC_URL` | - | hyperliquid testnet RPC endpoint |
| `--testnet/--no-testnet` | - | `False` | Use hyperliquid testnet instead of mainnet |
| `--dry-run/--no-dry-run` | - | `True` | Preview without sending transaction |
| `--private-key` | `PRIVATE_KEY` | - | Private key for signing (required if not dry-run) |

### Examples

**Dry-run on mainnet (safe):**

```bash
uv run tq-oracle --vault-address 0x277... --destination 0xabc... --dry-run
```

**Execute on testnet:**

```bash
uv run tq-oracle \
  --vault-address 0x277... \
  --destination 0xabc... \
  --testnet \
  --no-dry-run \
  --private-key 0x...
```

## Architecture

```sh
src/tq_oracle/
├── main.py                           # CLI entry point (Typer)
├── config.py                         # Configuration dataclass
├── orchestrator.py                   # Main control flow orchestration
├── adapters/
│   ├── __init__.py                   # Adapter registry
│   ├── asset_adapters/
│   │   ├── base.py                   # AssetAdapter base class
│   │   └── hyperliquid.py            # Hyperliquid asset fetching
│   └── price_adapters/
│       ├── base.py                   # PriceAdapter base class
│       └── chainlink.py              # Chainlink price feeds
├── processors/
│   ├── asset_aggregator.py           # Aggregate assets from adapters
│   ├── price_calculator.py           # Calculate relative prices
│   └── oracle_helper.py              # Derive final prices
├── report/
│   ├── generator.py                  # Generate oracle report
│   └── publisher.py                  # Publish to stdout/Safe
└── checks/
    └── pre_checks.py                 # Pre-flight validation

contracts/abis/                       # Contract ABIs (JSON)
├── Vault.json
├── Subvault.json
├── OracleHelper.json
├── EACAggregatorProxy.json
├── HyperliquidStrategy.json
└── ...
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
