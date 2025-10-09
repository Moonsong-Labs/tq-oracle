from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from eth_typing import URI
from web3 import Web3

if TYPE_CHECKING:
    from eth_typing import ChecksumAddress

ABIS_DIR = Path(__file__).parent / "abis"

ORACLE_ABI_PATH = ABIS_DIR / "IOracle.json"
ORACLE_HELPER_ABI_PATH = ABIS_DIR / "OracleHelper.json"
VAULT_ABI_PATH = ABIS_DIR / "Vault.json"
AGGREGATOR_ABI_PATH = ABIS_DIR / "AggregatorV3Interface.json"


def load_abi(path: str | Path) -> list[dict]:
    """Load an ABI from a JSON file and return its "abi" field.

    Args:
        path: Path to the JSON file containing an "abi" field.

    Returns:
        ABI as a list of dictionaries.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        KeyError: If the JSON does not contain an "abi" field.
    """
    p = Path(path)
    with p.open() as f:
        data = json.load(f)
    return data["abi"]


def load_oracle_abi() -> list[dict]:
    """Load the Oracle ABI."""
    return load_abi(ORACLE_ABI_PATH)


def load_oracle_helper_abi() -> list[dict]:
    """Load the OracleHelper ABI."""
    return load_abi(ORACLE_HELPER_ABI_PATH)


def load_vault_abi() -> list[dict]:
    """Load the Vault ABI."""
    return load_abi(VAULT_ABI_PATH)


def load_aggregator_abi() -> list[dict]:
    """Load the Aggregator ABI."""
    return load_abi(AGGREGATOR_ABI_PATH)


def get_oracle_address_from_vault(vault_address: str, rpc_url: str) -> ChecksumAddress:
    """Fetch the oracle address from the vault contract.

    Args:
        vault_address: The vault contract address
        rpc_url: RPC endpoint URL

    Returns:
        The oracle contract address from the vault

    Raises:
        ConnectionError: If RPC connection fails
        ValueError: If contract call fails
    """
    w3 = Web3(Web3.HTTPProvider(URI(rpc_url)))
    if not w3.is_connected():
        raise ConnectionError(f"Failed to connect to RPC: {rpc_url}")

    vault_abi = load_vault_abi()
    checksum_vault = w3.to_checksum_address(vault_address)
    vault_contract = w3.eth.contract(address=checksum_vault, abi=vault_abi)

    try:
        oracle_addr: ChecksumAddress = vault_contract.functions.oracle().call()
        return oracle_addr
    except Exception as e:
        raise ValueError(f"Failed to fetch oracle address from vault: {e}") from e
