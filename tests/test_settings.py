"""Tests for settings configuration loading."""

from __future__ import annotations

from textwrap import dedent

from tq_oracle.settings import OracleSettings


def test_promotes_root_flags_from_subvault_block(tmp_path, monkeypatch):
    """Ensure root-level flags defined after subvault adapters are respected."""

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        dedent(
            """
            vault_address = "0x123"
            vault_rpc = "https://rpc.example"
            dry_run = true

            [[subvault_adapters]]
            subvault_address = "0xabc"
            additional_adapters = ["idle_balances"]

            ignore_timeout_check = true
            ignore_empty_vault = true
            ignore_active_proposal_check = true
            pre_check_retries = 7
            pre_check_timeout = 42.5
            max_calls = 9
            rpc_max_concurrent_calls = 4
            rpc_delay = 0.33
            rpc_jitter = 0.21
            """
        ).strip()
    )

    monkeypatch.setenv("TQ_ORACLE_CONFIG", str(config_path))

    settings = OracleSettings()

    assert settings.ignore_timeout_check is True
    assert settings.ignore_empty_vault is True
    assert settings.ignore_active_proposal_check is True
    assert settings.pre_check_retries == 7
    assert settings.pre_check_timeout == 42.5
    assert settings.max_calls == 9
    assert settings.rpc_max_concurrent_calls == 4
    assert settings.rpc_delay == 0.33
    assert settings.rpc_jitter == 0.21

    assert settings.subvault_adapters == [
        {
            "subvault_address": "0xabc",
            "additional_adapters": ["idle_balances"],
        }
    ]
