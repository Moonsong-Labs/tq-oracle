import pytest

from tq_oracle.report.encoder import encode_submit_reports
from tq_oracle.report.generator import OracleReport


@pytest.fixture
def sample_oracle_address() -> str:
    return "0x1234567890123456789012345678901234567890"


@pytest.fixture
def sample_report() -> OracleReport:
    return OracleReport(
        vault_address="0xaaa1111111111111111111111111111111111111",
        base_asset="0xbbb2222222222222222222222222222222222222",
        total_assets={
            "0xbbb2222222222222222222222222222222222222": 1000000000000000000,
            "0xccc3333333333333333333333333333333333333": 2000000000000000000,
            "0xddd4444444444444444444444444444444444444": 3000000000000000000,
        },
        final_prices={
            "0xbbb2222222222222222222222222222222222222": 1500 * 10**18,
            "0xccc3333333333333333333333333333333333333": 2500 * 10**18,
            "0xddd4444444444444444444444444444444444444": 3500 * 10**18,
        },
    )


@pytest.fixture
def sample_empty_report() -> OracleReport:
    return OracleReport(
        vault_address="0xaaa1111111111111111111111111111111111111",
        base_asset="0xbbb2222222222222222222222222222222222222",
        total_assets={},
        final_prices={},
    )


def test_encode_submit_reports_multi_asset(
    sample_oracle_address: str, sample_report: OracleReport
):
    to_address, calldata = encode_submit_reports(sample_oracle_address, sample_report)

    assert isinstance(to_address, str)
    assert isinstance(calldata, bytes)
    assert to_address == sample_oracle_address
    assert len(calldata) > 0
    function_selector = calldata[:4].hex()
    assert function_selector == "8f88cbfb"


def test_encode_submit_reports_empty_report(
    sample_oracle_address: str, sample_empty_report: OracleReport
):
    to_address, calldata = encode_submit_reports(
        sample_oracle_address, sample_empty_report
    )

    assert isinstance(to_address, str)
    assert isinstance(calldata, bytes)
    assert to_address == sample_oracle_address
    assert len(calldata) > 0
    function_selector = calldata[:4].hex()
    assert function_selector == "8f88cbfb"


def test_base_asset_is_first_in_reports_array():
    """Verify that the base asset is always first in the reports array."""
    from web3 import Web3

    # Create a report where base asset would NOT be first numerically
    # 0xddd... > 0xccc... > 0xbbb... when sorted numerically
    # But we set base_asset to 0xddd..., so it should come first
    report = OracleReport(
        vault_address="0xaaa1111111111111111111111111111111111111",
        base_asset="0xddd4444444444444444444444444444444444444",  # Largest numerically
        total_assets={
            "0xbbb2222222222222222222222222222222222222": 1000000000000000000,
            "0xccc3333333333333333333333333333333333333": 2000000000000000000,
            "0xddd4444444444444444444444444444444444444": 3000000000000000000,
        },
        final_prices={
            "0xbbb2222222222222222222222222222222222222": 1500 * 10**18,
            "0xccc3333333333333333333333333333333333333": 2500 * 10**18,
            "0xddd4444444444444444444444444444444444444": 3500 * 10**18,
        },
    )

    oracle_address = "0x1234567890123456789012345678901234567890"
    to_address, calldata = encode_submit_reports(oracle_address, report)

    # Decode the calldata to verify ordering
    w3 = Web3()
    from tq_oracle.abi import load_oracle_abi

    abi = load_oracle_abi()
    contract = w3.eth.contract(address=w3.to_checksum_address(oracle_address), abi=abi)

    # Decode the transaction data
    func_obj, params = contract.decode_function_input(calldata)
    reports_array = params["reports"]

    # Verify base asset is first
    assert len(reports_array) == 3
    # Reports are dicts with 'asset' and 'priceD18' keys
    assert reports_array[0]["asset"] == w3.to_checksum_address(
        "0xddd4444444444444444444444444444444444444"
    )
    # Verify other assets are in numerical order
    assert reports_array[1]["asset"] == w3.to_checksum_address(
        "0xbbb2222222222222222222222222222222222222"
    )
    assert reports_array[2]["asset"] == w3.to_checksum_address(
        "0xccc3333333333333333333333333333333333333"
    )
