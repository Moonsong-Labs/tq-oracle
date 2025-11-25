"""Etherscan Logs API client for fetching event logs.

This module provides a reusable client for the Etherscan logs/getLogs API endpoint
"""

from typing import Any, Sequence, TypedDict

import backoff
import requests
from web3 import Web3
from web3.contract.contract import ContractEvent
from web3.types import EventData

from eth_typing import HexStr

from ..logger import get_logger

logger = get_logger(__name__)

ETHERSCAN_API_V2_URL = "https://api.etherscan.io/v2/api"


class EtherscanRateLimitError(Exception):
    """Raised when Etherscan returns a rate limit error."""

    pass


class EtherscanLogsResult(TypedDict, total=False):
    """Raw Etherscan API response for a single log entry."""

    address: str
    topics: list[str]
    data: str
    blockNumber: str
    blockHash: str
    timeStamp: str
    gasPrice: str
    gasUsed: str
    logIndex: str
    transactionHash: str
    transactionIndex: str


class EtherscanLogsResponse(TypedDict):
    """Complete Etherscan logs API response."""

    status: str
    message: str
    result: list[EtherscanLogsResult] | str


class EtherscanLogsClient:
    """Client for fetching event logs from Etherscan API v2.

    Provides async-compatible log fetching with:
    - Automatic pagination
    - Exponential backoff retry logic
    - Topic filtering support
    - Conversion to Web3.py EventData format
    """

    def __init__(
        self,
        api_key: str,
        chain_id: int,
        *,
        page_size: int = 1000,
        request_timeout: int = 15,
    ):
        """Initialize the Etherscan logs client.

        Args:
            api_key: Etherscan API key
            chain_id: Chain ID for the network (1 for mainnet, etc.)
            api_url: Base API URL (defaults to Etherscan v2 API)
            page_size: Number of results per page (max 1000)
            request_timeout: HTTP request timeout in seconds
        """
        self._api_key = api_key
        self._chain_id = chain_id
        self._page_size = max(1, min(page_size, 1000))
        self._request_timeout = request_timeout
        self._session = requests.Session()

    def fetch_logs(
        self,
        event: ContractEvent,
        contract_address: str,
        argument_filters: dict[str, str],
        from_block: int,
        to_block: int,
    ) -> list[EventData] | None:
        """Fetch and decode event logs from Etherscan.

        Args:
            event: Web3 ContractEvent to fetch logs for
            contract_address: Contract address to query
            argument_filters: Dict mapping indexed field names to filter values
            from_block: Starting block number
            to_block: Ending block number

        Returns:
            List of decoded EventData, or None if the request fails
        """
        abi = getattr(event, "abi", None)
        if not abi:
            return None

        topics = self._resolve_topics(event, argument_filters)
        if not topics or not topics[0]:
            return None

        logs: list[EventData] = []
        page = 1
        filter_desc = ", ".join(f"{k}={v}" for k, v in argument_filters.items())

        while True:
            payload = self._call(
                contract_address,
                topics,
                from_block,
                to_block,
                page,
            )
            if payload is None:
                return None

            status = payload.get("status", "").strip()
            message = payload.get("message", "").strip().lower()
            result = payload.get("result")

            if status != "1":
                if isinstance(result, str) and result.lower() == "no records found":
                    break
                if message == "no records found":
                    break
                logger.warning(
                    "Etherscan log query failed — event=%s filters={%s} blocks=[%d,%d] error=%s",
                    event.event_name,
                    filter_desc,
                    from_block,
                    to_block,
                    payload.get("result") or payload.get("message"),
                )
                return None

            if not isinstance(result, list):
                logger.warning("Unexpected Etherscan logs result: %s", result)
                return None

            for raw_log in result:
                decoded = self._process_log(event, raw_log)
                if decoded is not None:
                    logs.append(decoded)

            if len(result) < self._page_size:
                break
            page += 1

        logger.debug(
            "Etherscan query — event=%s filter={%s} found=%d",
            event.event_name,
            filter_desc,
            len(logs),
        )
        return logs

    @backoff.on_exception(
        backoff.expo,
        (requests.RequestException, ValueError, EtherscanRateLimitError),
        max_time=30,
        jitter=backoff.full_jitter,
    )
    def _call(
        self,
        contract_address: str,
        topics: Sequence[str | None],
        from_block: int,
        to_block: int,
        page: int,
    ) -> EtherscanLogsResponse | None:
        """Make a paginated request to the Etherscan logs API."""
        params: dict[str, Any] = {
            "chainid": str(self._chain_id),
            "module": "logs",
            "action": "getLogs",
            "address": contract_address,
            "fromBlock": str(from_block),
            "toBlock": str(to_block),
            "page": page,
            "offset": self._page_size,
            "sort": "asc",
            "apikey": self._api_key,
        }

        # Add topic filters
        topic0 = topics[0] if len(topics) > 0 else None
        topic1 = topics[1] if len(topics) > 1 else None
        topic2 = topics[2] if len(topics) > 2 else None

        if topic0:
            params["topic0"] = topic0
        if topic1:
            params["topic1"] = topic1
            params["topic0_1_opr"] = "and"
        if topic2:
            params["topic2"] = topic2
            params["topic0_2_opr"] = "and"

        response = self._session.get(
            ETHERSCAN_API_V2_URL,
            params=params,
            timeout=self._request_timeout,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Etherscan payload format")

        result = payload.get("result", "")
        if isinstance(result, str) and "rate limit" in result.lower():
            raise EtherscanRateLimitError(result)

        return payload  # type: ignore[return-value]

    def _resolve_topics(
        self,
        event: ContractEvent,
        argument_filters: dict[str, str],
    ) -> list[str | None]:
        """Extract Ethereum log topics from a contract event with filters."""
        try:
            params = event._get_event_filter_params(event.abi, argument_filters)
        except Exception:
            return []

        topics = params.get("topics") or []
        resolved: list[str | None] = []

        for index in range(len(topics)):
            resolved.append(self._extract_topic(topics, index))

        return resolved

    @staticmethod
    def _extract_topic(topics: Sequence[Any], index: int) -> str | None:
        """Safely extract and convert a single topic to hex string."""
        if len(topics) <= index:
            return None

        value = topics[index]
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            if isinstance(value, bytearray):
                value = bytes(value)
            return Web3.to_hex(value)
        if isinstance(value, str):
            return value
        return Web3.to_hex(value)

    def _process_log(
        self,
        event: ContractEvent,
        raw_log: EtherscanLogsResult,
    ) -> EventData | None:
        """Decode a raw Etherscan log using the contract event."""
        try:
            formatted = self._format_log(raw_log)
            return event.process_log(formatted)
        except Exception:
            return None

    @staticmethod
    def _format_log(raw_log: EtherscanLogsResult) -> dict[str, Any]:
        """Convert Etherscan API log format to Web3.py EventLog format."""

        def to_int(value: str | None) -> int:
            if not value:
                return 0
            return Web3.to_int(hexstr=HexStr(value))

        data_hex = raw_log.get("data") or "0x"
        block_hash_hex = raw_log.get("blockHash") or "0x0"
        tx_hash_hex = raw_log.get("transactionHash") or "0x0"
        topics_hex = raw_log.get("topics", []) or []

        return {
            "address": raw_log.get("address"),
            "blockHash": block_hash_hex,
            "blockNumber": to_int(raw_log.get("blockNumber")),
            "data": data_hex,
            "logIndex": to_int(raw_log.get("logIndex")),
            "topics": [
                Web3.to_bytes(hexstr=HexStr(topic)) for topic in topics_hex if topic
            ],
            "transactionHash": tx_hash_hex,
            "transactionIndex": to_int(raw_log.get("transactionIndex")),
        }
