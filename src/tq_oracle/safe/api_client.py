"""Safe API client for interacting with Safe Transaction Service."""

from __future__ import annotations

import logging

import requests
from eth_utils import keccak
from web3 import Web3

from .constants import NETWORK_PREFIXES, SAFE_SERVICE_URLS

logger = logging.getLogger(__name__)


def get_safe_service_url(chain_id: int) -> str:
    """Get Safe Transaction Service URL for chain.

    Args:
        chain_id: Network chain ID (e.g., 1 for mainnet, 11155111 for sepolia)

    Returns:
        Safe Transaction Service API URL

    Raises:
        ValueError: If chain_id is not supported
    """
    if chain_id not in SAFE_SERVICE_URLS:
        raise ValueError(
            f"Unsupported chain_id: {chain_id}. "
            f"Supported chains: {list(SAFE_SERVICE_URLS.keys())}"
        )
    return SAFE_SERVICE_URLS[chain_id]


class SafeAPIClient:
    """Client for interacting with Safe Transaction Service using requests library."""

    def __init__(self, chain_id: int, safe_address: str, rpc_url: str):
        """Initialize Safe API client.

        Args:
            chain_id: Network chain ID
            safe_address: Gnosis Safe contract address
            rpc_url: Ethereum RPC endpoint URL (unused, kept for compatibility)
        """
        self.chain_id = chain_id
        self.safe_address = Web3.to_checksum_address(safe_address)
        self.service_url = get_safe_service_url(chain_id)
        self.session = requests.Session()

    def get_safe_info(self) -> dict[str, object]:
        """Fetch Safe configuration (owners, threshold, nonce).

        Returns:
            Dictionary with owners, threshold, and nonce

        Raises:
            requests.HTTPError: If fetching Safe info fails
        """
        try:
            response = self.session.get(
                f"{self.service_url}/api/v1/safes/{self.safe_address}/"
            )
            response.raise_for_status()
            info = response.json()

            return {
                "owners": info.get("owners", []),
                "threshold": info.get("threshold", 0),
                "nonce": info.get("nonce", 0),
            }
        except requests.HTTPError as e:
            logger.error("Failed to fetch Safe info: %s", e)
            raise

    def calculate_safe_tx_hash(
        self,
        to: str,
        value: int,
        data: bytes,
        operation: int,
        safe_tx_gas: int,
        base_gas: int,
        gas_price: int,
        gas_token: str,
        refund_receiver: str,
        nonce: int,
    ) -> str:
        """Calculate Safe transaction hash using EIP-712.

        This follows the exact implementation from Safe.sol:getTransactionHash()

        Args:
            to: Destination address
            value: ETH value to send
            data: Transaction calldata
            operation: 0 for CALL, 1 for DELEGATECALL
            safe_tx_gas: Gas for Safe transaction execution
            base_gas: Base gas cost
            gas_price: Gas price
            gas_token: Token address for gas payment
            refund_receiver: Address receiving gas refund
            nonce: Safe nonce

        Returns:
            Safe transaction hash (contractTransactionHash)
        """
        # EIP-712 typehashes from Safe.sol
        DOMAIN_SEPARATOR_TYPEHASH = keccak(
            b"EIP712Domain(uint256 chainId,address verifyingContract)"
        )
        SAFE_TX_TYPEHASH = keccak(
            b"SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)"
        )

        safe_address_bytes = bytes.fromhex(self.safe_address[2:])
        domain_separator = keccak(
            DOMAIN_SEPARATOR_TYPEHASH
            + self.chain_id.to_bytes(32, "big")
            + safe_address_bytes.rjust(32, b"\x00")
        )

        data_hash = keccak(data)

        to_bytes = bytes.fromhex(Web3.to_checksum_address(to)[2:])
        gas_token_bytes = bytes.fromhex(Web3.to_checksum_address(gas_token)[2:])
        refund_receiver_bytes = bytes.fromhex(
            Web3.to_checksum_address(refund_receiver)[2:]
        )

        safe_tx_hash_data = (
            SAFE_TX_TYPEHASH
            + to_bytes.rjust(32, b"\x00")
            + value.to_bytes(32, "big")
            + data_hash
            + operation.to_bytes(32, "big")
            + safe_tx_gas.to_bytes(32, "big")
            + base_gas.to_bytes(32, "big")
            + gas_price.to_bytes(32, "big")
            + gas_token_bytes.rjust(32, b"\x00")
            + refund_receiver_bytes.rjust(32, b"\x00")
            + nonce.to_bytes(32, "big")
        )

        safe_tx_hash_struct = keccak(safe_tx_hash_data)

        # Final EIP-712 hash: keccak256("\x19\x01" || domainSeparator || structHash)
        final_hash = keccak(b"\x19\x01" + domain_separator + safe_tx_hash_struct)

        return "0x" + final_hash.hex()

    def propose_transaction(
        self,
        to: str,
        data: bytes,
        value: int = 0,
        operation: int = 0,
        safe_tx_gas: int = 0,
        base_gas: int = 0,
        gas_price: int = 0,
        gas_token: str = "0x0000000000000000000000000000000000000000",
        refund_receiver: str = "0x0000000000000000000000000000000000000000",
        origin: str | None = None,
        sender: str | None = None,
    ) -> str:
        """Propose transaction to Safe for signing.

        Args:
            to: Destination address
            data: Transaction calldata
            value: ETH value to send (default: 0)
            operation: 0 for CALL, 1 for DELEGATECALL (default: 0)
            safe_tx_gas: Gas for Safe transaction execution (default: 0)
            base_gas: Base gas cost (default: 0)
            gas_price: Gas price (default: 0)
            gas_token: Token address for gas payment (default: ETH)
            refund_receiver: Address receiving gas refund (default: zero address)
            origin: Optional origin identifier
            sender: Address proposing the transaction (defaults to first owner)

        Returns:
            Safe transaction hash

        Raises:
            requests.HTTPError: If proposing transaction fails
        """
        safe_info = self.get_safe_info()
        nonce = safe_info["nonce"]
        owners = safe_info["owners"]

        if sender is None:
            if not isinstance(owners, list) or len(owners) == 0:
                raise ValueError("Safe has no owners")
            sender = owners[0]

        if not isinstance(nonce, int):
            nonce = 0

        safe_tx_hash = self.calculate_safe_tx_hash(
            to=to,
            value=value,
            data=data,
            operation=operation,
            safe_tx_gas=safe_tx_gas,
            base_gas=base_gas,
            gas_price=gas_price,
            gas_token=gas_token,
            refund_receiver=refund_receiver,
            nonce=nonce,
        )

        payload = {
            "to": Web3.to_checksum_address(to),
            "value": str(value),
            "data": data.hex() if isinstance(data, bytes) else data,
            "operation": operation,
            "safeTxGas": str(safe_tx_gas),
            "baseGas": str(base_gas),
            "gasPrice": str(gas_price),
            "gasToken": gas_token,
            "refundReceiver": refund_receiver,
            "nonce": nonce,
            "contractTransactionHash": safe_tx_hash,
            "sender": Web3.to_checksum_address(sender),
        }

        if origin:
            payload["origin"] = origin

        # POST to Safe Transaction Service
        response = self.session.post(
            f"{self.service_url}/api/v1/safes/{self.safe_address}/multisig-transactions/",
            json=payload,
        )

        try:
            response.raise_for_status()
            # 201 Created may have empty body, return calculated hash
            if response.status_code == 201:
                logger.info("Transaction proposed successfully: %s", safe_tx_hash)
                return safe_tx_hash
            result = response.json()
            return result.get("safeTxHash", safe_tx_hash)
        except requests.HTTPError as e:
            logger.error("Failed to propose transaction: %s - %s", e, response.text)
            raise

    def get_safe_ui_url(self, safe_tx_hash: str) -> str:
        """Generate Safe UI URL for transaction.

        Args:
            safe_tx_hash: Safe transaction hash

        Returns:
            Safe web app URL for the transaction
        """
        network_prefix = NETWORK_PREFIXES.get(self.chain_id, "eth")
        return (
            f"https://app.safe.global/transactions/queue"
            f"?safe={network_prefix}:{self.safe_address}"
            f"#{safe_tx_hash}"
        )
