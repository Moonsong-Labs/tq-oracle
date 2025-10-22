from tq_oracle.config import OracleCLIConfig


def test_as_safe_dict_with_private_key():
    """Private key should be redacted in safe dict."""
    config = OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        l1_rpc="https://eth.example",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc="https://hl.example",
        hl_subvault_address=None,
        testnet=False,
        dry_run=False,
        private_key="0x1234567890abcdef",
        safe_txn_srvc_api_key="0xSAFE",
    )

    safe_dict = config.as_safe_dict()

    assert safe_dict["private_key"] == "***redacted***"
    assert safe_dict["vault_address"] == "0xVAULT"
    assert safe_dict["l1_rpc"] == "https://eth.example"


def test_as_safe_dict_without_private_key():
    """Config without private key should not add redaction."""
    config = OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        l1_rpc="https://eth.example",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc=None,
        hl_subvault_address=None,
        testnet=True,
        dry_run=True,
        private_key=None,
        safe_txn_srvc_api_key=None,
    )

    safe_dict = config.as_safe_dict()

    assert safe_dict["private_key"] is None
    assert safe_dict["testnet"] is True


def test_as_safe_dict_preserves_all_fields():
    """All config fields should be present in safe dict."""
    config = OracleCLIConfig(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        l1_rpc="https://eth.example",
        l1_subvault_address=None,
        safe_address=None,
        hl_rpc="https://hl.example",
        hl_subvault_address=None,
        testnet=False,
        dry_run=True,
        private_key="0xSECRET",
        safe_txn_srvc_api_key="0xSAFE",
    )

    safe_dict = config.as_safe_dict()

    assert set(safe_dict.keys()) == {
        "vault_address",
        "oracle_helper_address",
        "l1_rpc",
        "l1_subvault_address",
        "safe_address",
        "hl_rpc",
        "hl_subvault_address",
        "testnet",
        "dry_run",
        "private_key",
        "safe_txn_srvc_api_key",
        "ignore_empty_vault",
        "ignore_timeout_check",
        "ignore_active_proposal_check",
        "using_default_rpc",
        "pre_check_retries",
        "pre_check_timeout",
        "_chain_id",
        "_oracle_address",
        "rpc_delay",
        "rpc_max_concurrent_calls",
        "max_calls",
        "rpc_jitter",
        "chainlink_price_warning_tolerance_percentage",
        "chainlink_price_failure_tolerance_percentage",
        "log_level",
        "subvault_adapters",
    }
