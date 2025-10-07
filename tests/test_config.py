from tq_oracle.config import OracleCLIConfig


def test_as_safe_dict_with_private_key():
    """Private key should be redacted in safe dict."""
    config = OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        destination="0xDEST",
        mainnet_rpc="https://eth.example",
        hl_rpc="https://hl.example",
        testnet=False,
        dry_run=False,
        backoff=True,
        private_key="0x1234567890abcdef",
    )

    safe_dict = config.as_safe_dict()

    assert safe_dict["private_key"] == "***redacted***"
    assert safe_dict["vault_address"] == "0xVAULT"
    assert safe_dict["mainnet_rpc"] == "https://eth.example"


def test_as_safe_dict_without_private_key():
    """Config without private key should not add redaction."""
    config = OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        destination="0xDEST",
        mainnet_rpc="https://eth.example",
        hl_rpc=None,
        testnet=True,
        dry_run=True,
        backoff=False,
        private_key=None,
    )

    safe_dict = config.as_safe_dict()

    assert safe_dict["private_key"] is None
    assert safe_dict["testnet"] is True


def test_as_safe_dict_preserves_all_fields():
    """All config fields should be present in safe dict."""
    config = OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        destination="0xDEST",
        mainnet_rpc="https://eth.example",
        hl_rpc="https://hl.example",
        testnet=False,
        dry_run=True,
        backoff=True,
        private_key="0xSECRET",
    )

    safe_dict = config.as_safe_dict()

    assert set(safe_dict.keys()) == {
        "vault_address",
        "oracle_helper_address",
        "destination",
        "mainnet_rpc",
        "hl_rpc",
        "testnet",
        "dry_run",
        "backoff",
        "private_key",
    }
