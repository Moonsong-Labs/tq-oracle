import pytest

from tq_oracle.adapters.price_adapters.pyth import PythAdapter
from tq_oracle.settings import Network, OracleSettings


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0xVault",
        oracle_helper_address="0xOracleHelper",
        vault_rpc="https://eth.drpc.org",
        network=Network.MAINNET,
        safe_address=None,
        dry_run=False,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )


@pytest.fixture
def adapter(config):
    return PythAdapter(config)


def test_adapter_name(adapter):
    assert adapter.adapter_name == "pyth"


def test_check_confidence_passes_with_low_confidence(adapter):
    price_obj = {"price": "100000000", "conf": "1000000", "expo": -8}
    price_18 = 1000000000000000000
    adapter._check_confidence(price_obj, price_18, "ETH/USD")


def test_check_confidence_fails_with_high_confidence(adapter):
    price_obj = {"price": "100000000", "conf": "5000000", "expo": -8}
    price_18 = 1000000000000000000

    with pytest.raises(ValueError, match=r"confidence ratio .* exceeds maximum"):
        adapter._check_confidence(price_obj, price_18, "ETH/USD")


def test_check_confidence_fails_on_zero_price(adapter):
    price_obj = {"price": "0", "conf": "1000000", "expo": -8}
    price_18 = 0

    with pytest.raises(ValueError, match="price is zero"):
        adapter._check_confidence(price_obj, price_18, "ETH/USD")
