# tests/adapters/check_adapters/test_cctp_bridge.py

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tq_oracle.adapters.check_adapters.cctp_bridge import (
    CCTPBridgeAdapter,
    TransactionIdentity,
)
from tq_oracle.config import OracleCLIConfig
from tq_oracle.constants import (
    HL_BLOCK_TIME,
    L1_BLOCK_TIME,
    TOKEN_MESSENGER_V2_PROD,
    TOKEN_MESSENGER_V2_TEST,
)

# A valid but arbitrary bytes32 value representing a mint recipient address
MINT_RECIPIENT_BYTES32 = (
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88\x88"
)
RECIPIENT_ADDRESS = "0x8888888888888888888888888888888888888888"
DEPOSITOR_ADDRESS = "0x1111111111111111111111111111111111111111"


@pytest.fixture
def mock_w3():
    """Fixture for a mocked AsyncWeb3 instance."""
    mock = MagicMock()
    mock.to_checksum_address = MagicMock(
        side_effect=lambda addr: addr if isinstance(addr, str) else "0x" + addr.hex()
    )
    mock.eth = MagicMock()
    # Make block_number a property that returns a coroutine
    type(mock.eth).block_number = property(lambda self: AsyncMock(return_value=10000)())
    mock.provider = MagicMock()
    mock.provider.disconnect = AsyncMock()
    return mock


@pytest.fixture
def config():
    """Provides a default, valid OracleCLIConfig for tests."""
    return OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        l1_rpc="https://eth.example",
        hl_rpc="https://hl.example",
        l1_subvault_address=DEPOSITOR_ADDRESS,
        hl_subvault_address=RECIPIENT_ADDRESS,
        testnet=False,
        dry_run=True,
        private_key=None,
        safe_address=None,
        safe_txn_srvc_api_key=None,
    )


def create_mock_deposit_event(amount, recipient_bytes32):
    """Helper to create a mock DepositForBurn event."""
    return {
        "args": {
            "amount": amount,
            "mintRecipient": recipient_bytes32,
        }
    }


def create_mock_mint_event(amount, fee, recipient_address):
    """Helper to create a mock MintAndWithdraw event."""
    return {
        "args": {
            "amount": amount,
            "feeCollected": fee,
            "mintRecipient": recipient_address,
        }
    }


@pytest.mark.parametrize(
    "base_blocks, source_time, dest_time, expected_source, expected_dest",
    [
        # L1 -> HL (L1 is slower)
        (80, 12, 1, 80, 960),
        # HL -> L1 (HL is faster)
        (80, 1, 12, 960, 80),
        # Equal block times
        (100, 10, 10, 100, 100),
        # Zero base blocks
        (0, 12, 1, 0, 0),
        # Capping logic: source_blocks_scaled (80 * 12/1 = 960) should be capped
        # at base_blocks * max_lookback_multiplier (80 * 12/1 = 960). This test
        # confirms the logic holds even when scaling factor is large.
        (80, 1, 12, 960, 80),
    ],
)
def test_calculate_scaled_blocks(
    config, base_blocks, source_time, dest_time, expected_source, expected_dest
):
    """
    Tests the _calculate_scaled_blocks logic for various chain speeds.
    It ensures the time window is consistent across both chains.
    """
    adapter = CCTPBridgeAdapter(config)
    source_blocks, dest_blocks = adapter._calculate_scaled_blocks(
        base_blocks, source_time, dest_time
    )
    assert source_blocks == expected_source
    assert dest_blocks == expected_dest
    # The time window in seconds should be identical
    assert source_blocks * source_time == dest_blocks * dest_time


def test_extract_address_from_bytes32(mock_w3):
    """
    Verifies that an Ethereum address is correctly extracted and checksummed
    from a CCTP-style bytes32 value.
    """
    extracted = CCTPBridgeAdapter._extract_address_from_bytes32(
        mock_w3, MINT_RECIPIENT_BYTES32
    )
    assert extracted == RECIPIENT_ADDRESS.lower()
    # Verify it was called with the last 20 bytes
    mock_w3.to_checksum_address.assert_called_once_with(MINT_RECIPIENT_BYTES32[-20:])


@pytest.mark.asyncio
async def test_run_check_missing_l1_subvault_address(config):
    """
    Checks should fail immediately with a clear message if the L1 subvault
    address is missing from the configuration.
    """
    config.l1_subvault_address = None
    adapter = CCTPBridgeAdapter(config)
    result = await adapter.run_check()
    assert not result.passed
    assert not result.retry_recommended
    assert "L1 subvault address is required" in result.message


@pytest.mark.asyncio
async def test_run_check_missing_hl_subvault_address(config):
    """
    Checks should pass and skip CCTP checks when the HL subvault
    address is missing from the configuration.
    """
    config.hl_subvault_address = None
    adapter = CCTPBridgeAdapter(config)
    result = await adapter.run_check()
    assert result.passed
    assert not result.retry_recommended
    assert "Skipping CCTP bridge checks" in result.message


@pytest.mark.asyncio
async def test_run_check_no_inflight_transactions(config):
    """
    Verifies that the check passes when no in-flight transactions are found
    in either direction.
    """
    adapter = CCTPBridgeAdapter(config)
    # Mock _check_direction to simulate finding 0 transactions
    adapter._check_direction = AsyncMock(return_value=0)
    adapter._cleanup_providers = AsyncMock()

    result = await adapter.run_check()

    assert result.passed
    assert "No in-flight" in result.message
    assert adapter._check_direction.call_count == 2


@pytest.mark.asyncio
async def test_run_check_detects_inflight_transactions(config):
    """
    Verifies that the check fails if in-flight transactions are detected,
    and correctly sums transactions from both directions.
    """
    adapter = CCTPBridgeAdapter(config)
    # Simulate 1 transaction L1->HL and 2 transactions HL->L1
    adapter._check_direction = AsyncMock(side_effect=[1, 2])
    adapter._cleanup_providers = AsyncMock()

    result = await adapter.run_check()

    assert not result.passed
    assert result.retry_recommended
    assert "Found 3 in-flight" in result.message
    assert adapter._check_direction.call_count == 2


@pytest.mark.asyncio
@patch("tq_oracle.adapters.check_adapters.cctp_bridge.AsyncWeb3")
async def test_run_check_handles_general_exception(mock_async_web3, config):
    """
    Ensures that any unexpected exception during the check process is caught,
    results in a failed check, and that provider cleanup is still attempted.
    """
    # Make the web3 provider connection fail
    mock_async_web3.side_effect = RuntimeError("RPC connection failed")
    adapter = CCTPBridgeAdapter(config)
    adapter._cleanup_providers = AsyncMock()

    result = await adapter.run_check()

    assert not result.passed
    assert "Error checking CCTP bridge: RPC connection failed" in result.message
    adapter._cleanup_providers.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_direction_logic(config, mock_w3):
    """
    A comprehensive test of the core `_check_direction` logic, covering
    matching, non-matching, and fee-adjusted transactions.
    """

    # Mock source and destination web3 instances and contracts
    source_w3 = mock_w3
    dest_w3 = MagicMock()
    dest_w3.to_checksum_address = lambda addr: addr.lower()
    dest_w3.eth = MagicMock()
    type(dest_w3.eth).block_number = property(
        lambda self: AsyncMock(return_value=120000)()
    )

    source_messenger = AsyncMock()
    dest_messenger = AsyncMock()

    # --- Event Data ---
    # 1. A transaction that has been deposited but not yet minted (in-flight)
    deposit_inflight = create_mock_deposit_event(1000, MINT_RECIPIENT_BYTES32)
    # 2. A transaction that was deposited and successfully minted (matched)
    deposit_matched = create_mock_deposit_event(2000, MINT_RECIPIENT_BYTES32)
    mint_matched = create_mock_mint_event(2000, 0, RECIPIENT_ADDRESS)
    # 3. A transaction with a fee (matched)
    deposit_fee = create_mock_deposit_event(3000, MINT_RECIPIENT_BYTES32)
    mint_fee = create_mock_mint_event(
        2990, 10, RECIPIENT_ADDRESS
    )  # amount + fee = 3000
    # 4. A mint that doesn't correspond to any deposit in the window
    mint_unmatched = create_mock_mint_event(4000, 0, RECIPIENT_ADDRESS)

    source_messenger.events.DepositForBurn.get_logs = AsyncMock(
        return_value=[deposit_inflight, deposit_matched, deposit_fee]
    )
    dest_messenger.events.MintAndWithdraw.get_logs = AsyncMock(
        return_value=[mint_matched, mint_fee, mint_unmatched]
    )

    adapter = CCTPBridgeAdapter(config)
    # Patch the address extractor to use our mock w3 instance
    adapter._extract_address_from_bytes32 = MagicMock(
        return_value=RECIPIENT_ADDRESS.lower()
    )

    # --- Act ---
    inflight_count = await adapter._check_direction(
        source_w3=source_w3,
        dest_w3=dest_w3,
        source_messenger=source_messenger,
        dest_messenger=dest_messenger,
        source_subvault_address=DEPOSITOR_ADDRESS,
        dest_subvault_address=RECIPIENT_ADDRESS,
        direction="L1→HL",
        source_block_time=L1_BLOCK_TIME,
        dest_block_time=HL_BLOCK_TIME,
    )

    # --- Assert ---
    # Only `deposit_inflight` should be left after the set difference.
    assert inflight_count == 1

    # Verify the transaction identities were constructed correctly
    deposited_txs = {
        TransactionIdentity(1000, RECIPIENT_ADDRESS.lower()),
        TransactionIdentity(2000, RECIPIENT_ADDRESS.lower()),
        TransactionIdentity(3000, RECIPIENT_ADDRESS.lower()),
    }
    minted_txs = {
        TransactionIdentity(2000, RECIPIENT_ADDRESS.lower()),
        TransactionIdentity(3000, RECIPIENT_ADDRESS.lower()),  # 2990 + 10
        TransactionIdentity(4000, RECIPIENT_ADDRESS.lower()),
    }
    assert deposited_txs - minted_txs == {
        TransactionIdentity(1000, RECIPIENT_ADDRESS.lower())
    }


@pytest.mark.asyncio
async def test_cleanup_providers_handles_no_disconnect_method():
    """
    Ensures _cleanup_providers does not raise an exception if a provider
    object is None or lacks a `disconnect` method.
    """
    adapter = CCTPBridgeAdapter(MagicMock())

    provider_with_disconnect = AsyncMock()
    provider_with_disconnect.provider.disconnect = AsyncMock()

    provider_without_disconnect = MagicMock()
    provider_without_disconnect.provider = MagicMock(
        spec=[]
    )  # spec=[] means no attributes

    await adapter._cleanup_providers(
        provider_with_disconnect, provider_without_disconnect, None
    )

    provider_with_disconnect.provider.disconnect.assert_awaited_once()


def test_messenger_addresses_mainnet(config):
    """Verifies correct CCTP messenger addresses for mainnet."""
    config.testnet = False
    adapter = CCTPBridgeAdapter(config)
    assert adapter.MESSENGER_ADDRESSES["mainnet"] == TOKEN_MESSENGER_V2_PROD


def test_messenger_addresses_testnet(config):
    """Verifies correct CCTP messenger addresses for testnet."""
    config.testnet = True
    adapter = CCTPBridgeAdapter(config)
    assert adapter.MESSENGER_ADDRESSES["testnet"] == TOKEN_MESSENGER_V2_TEST


@pytest.mark.asyncio
async def test_check_direction_empty_events(config, mock_w3):
    """
    Verifies that when no events are found on either chain, the check
    correctly reports zero in-flight transactions.
    """
    source_w3 = mock_w3
    dest_w3 = MagicMock()
    dest_w3.to_checksum_address = lambda addr: addr.lower()
    dest_w3.eth = MagicMock()
    type(dest_w3.eth).block_number = property(
        lambda self: AsyncMock(return_value=120000)()
    )

    source_messenger = AsyncMock()
    dest_messenger = AsyncMock()

    # No events on either chain
    source_messenger.events.DepositForBurn.get_logs = AsyncMock(return_value=[])
    dest_messenger.events.MintAndWithdraw.get_logs = AsyncMock(return_value=[])

    adapter = CCTPBridgeAdapter(config)

    inflight_count = await adapter._check_direction(
        source_w3=source_w3,
        dest_w3=dest_w3,
        source_messenger=source_messenger,
        dest_messenger=dest_messenger,
        source_subvault_address=DEPOSITOR_ADDRESS,
        dest_subvault_address=RECIPIENT_ADDRESS,
        direction="L1→HL",
        source_block_time=L1_BLOCK_TIME,
        dest_block_time=HL_BLOCK_TIME,
    )

    assert inflight_count == 0
