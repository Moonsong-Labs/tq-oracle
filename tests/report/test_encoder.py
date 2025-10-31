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
