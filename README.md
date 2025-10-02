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
tq-oracle \
  --vault-address 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --destination 0xYourDestinationAddress \
  --mainnet-rpc https://eth.drpc.org \
  --hl-rpc https://your-hyperlane-rpc \
  --dry-run
```

### With Environment Variables

Create a `.env` file:

```env
MAINNET_RPC_URL=https://eth.drpc.org
HL_RPC_URL=https://your-hyperlane-rpc
PRIVATE_KEY=0xYourPrivateKey
```

Then run:

```bash
tq-oracle \
  --vault-address 0x277C6A642564A91ff78b008022D65683cEE5CCC5 \
  --destination 0xYourDestinationAddress
```

### CLI Options

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `--vault-address` | - | *required* | Vault contract address to query |
| `--destination` | - | *required* | Destination EOA for transaction |
| `--mainnet-rpc` | `MAINNET_RPC_URL` | `https://eth.drpc.org` | Ethereum mainnet RPC endpoint |
| `--hl-rpc` | `HL_RPC_URL` | - | Hyperlane testnet RPC endpoint |
| `--testnet/--no-testnet` | - | `False` | Use Hyperlane testnet instead of mainnet |
| `--dry-run/--no-dry-run` | - | `True` | Preview without sending transaction |
| `--backoff/--no-backoff` | - | `True` | Enable exponential backoff retry |
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

**With retry disabled:**
```bash
uv run tq-oracle \
  --vault-address 0x277... \
  --destination 0xabc... \
  --no-backoff
```

## Architecture

```
src/
├── main.py                      # CLI entry point (Typer)
├── models/
│   ├── config.py                # Configuration validation (Pydantic)
│   └── oracle_report.py         # Data models (AssetPrice, OracleReport)
├── core/
│   ├── web3_client.py           # Web3 connection management
│   ├── oracle_manager.py        # Adapter orchestration
│   └── transaction_builder.py  # Transaction preparation & signing
├── adapters/
│   ├── base_adapter.py          # Abstract base class
│   ├── fe_oracle_adapter.py     # FE Oracle TVL queries
│   ├── wsteth_adapter.py        # wstETH price conversion
│   └── oracle_helper_adapter.py # OracleHelper price aggregation
└── utils/
    ├── abi_loader.py            # ABI file loading with caching
    └── retry.py                 # Exponential backoff decorator

contracts/
└── abis/                        # Contract ABIs (JSON)
    ├── FEOracle.json
    ├── OracleHelper.json
    └── wstETH.json
```

## Adding New Protocol Adapters

1. **Create adapter file** in `src/adapters/`:

```python
# src/adapters/my_protocol_adapter.py
from web3 import Web3
from ..models.oracle_report import AssetPrice
from ..models.config import OracleConfig
from ..utils.abi_loader import load_abi
from .base_adapter import BaseAdapter

class MyProtocolAdapter(BaseAdapter):
    CONTRACT_ADDRESS = "0x..."

    def __init__(self, w3: Web3, config: OracleConfig):
        super().__init__(w3, config)
        self.contract = w3.eth.contract(
            address=Web3.to_checksum_address(self.CONTRACT_ADDRESS),
            abi=load_abi("MyProtocol")
        )

    @property
    def adapter_name(self) -> str:
        return "my_protocol"

    def get_asset_prices(self, vault: str, block_number: int) -> list[AssetPrice]:
        # Your implementation here
        price = self.contract.functions.getPrice().call(block_identifier=block_number)
        return [AssetPrice(asset="0x...", price_d18=price)]
```

2. **Add ABI file** to `contracts/abis/MyProtocol.json`

3. **Import in registry** (`src/adapters/__init__.py`):

```python
from . import my_protocol_adapter

# Add to module list in get_all_adapters()
```

The adapter will be automatically discovered and executed!

## Output Format

```json
{
  "vault": "0x277C6A642564A91ff78b008022D65683cEE5CCC5",
  "block_number": 12345678,
  "total_assets": 1000000000000000000,
  "reports": [
    {
      "asset": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
      "price_d18": 1150000000000000000
    },
    {
      "asset": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
      "price_d18": 1000000000000000000
    }
  ]
}
```

## Security Considerations

- **Private Keys**: Always use environment variables, never commit to git
- **Dry-run Default**: Application defaults to dry-run mode for safety
- **RPC Endpoints**: Use trusted RPC providers
- **Transaction Validation**: Review dry-run output before execution
- **Gas Limits**: Monitor transaction gas costs (future enhancement)

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

## Troubleshooting

**RPC Connection Failed**
- Verify RPC URL is accessible
- Check firewall/network settings
- Try alternative RPC provider

**Adapter Errors**
- Ensure ABIs are correctly extracted
- Verify contract addresses are checksummed
- Check block number is valid

**Transaction Failures**
- Ensure sufficient gas (if not dry-run)
- Verify private key has signing permission
- Check destination contract accepts format

---

## External Links

- `flexible-vaults` [repo](https://github.com/mellow-finance/flexible-vaults)
- Hyperliquid API [documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- `cctp-v2` [contracts](https://github.com/circlefin/evm-cctp-contracts/tree/master/src/v2)
- DeBridge [contracts](https://github.com/debridge-finance/dln-contracts/tree/main/contracts/DLN)

## License

MIT
