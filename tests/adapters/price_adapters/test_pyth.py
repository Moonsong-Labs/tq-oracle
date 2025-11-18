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


class TestScaleTo18:
    def test_scale_to_18_typical_pyth_expo(self, adapter):
        result = adapter._scale_to_18(250012345678, -8)
        assert result == 2500123456780000000000

    def test_scale_to_18_negative_price_rejected(self, adapter):
        with pytest.raises(ValueError, match="Price value must be non-negative"):
            adapter._scale_to_18(-12345, -8)

    def test_scale_to_18_overflow(self, adapter):
        with pytest.raises(ValueError, match="exceeds uint256 max"):
            adapter._scale_to_18(10**70, 0)
