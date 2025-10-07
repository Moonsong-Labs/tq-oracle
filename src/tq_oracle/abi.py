from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

ORACLE_HELPER_ABI_PATH = PROJECT_ROOT / "abis" / "OracleHelper.json"


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


def load_oracle_helper_abi() -> list[dict]:
    """Load the OracleHelper ABI."""
    return load_abi(ORACLE_HELPER_ABI_PATH)
