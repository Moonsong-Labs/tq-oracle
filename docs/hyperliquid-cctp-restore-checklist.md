# Hyperliquid & CCTP Restore Checklist

Use this checklist when you are ready to ship Hyperliquid support and the CCTP pre-check again. Work through every section before exposing the functionality.

## 1. Dependencies

- [ ] Add the hyperliquid sdk back to `pyproject.toml` and run **uv sync** to update `uv.lock`.
- [ ] Confirm RPC providers and API endpoints for the target Hyperliquid environment(s).

## 2. Configuration & CLI Surface

- [ ] Restore Hyperliquid/CCTP fields in `OracleSettings` (environment toggles, RPC/subvault fields, token messenger settings).
- [ ] Reinstate logging/telemetry in `pipeline/run.py` that records Hyperliquid and CCTP settings.
- [ ] Reintroduce CLI flags for Hyperliquid/CCTP in `main.py` (`--hyperliquid-env`, `--hl-rpc`, `--hl-block-number`, `--cctp-env`).
- [ ] Update documentation (README/ARCHITECTURE) and sample configs once fields exist again.

## 3. Runtime Wiring

- [ ] Re-register `HyperliquidAdapter` in `src/tq_oracle/adapters/asset_adapters/__init__.py`.
- [ ] Allow `collect_assets` to schedule Hyperliquid adapters instead of skipping disabled entries.
- [ ] Ensure idle balances on Hyperliquid still function (`IdleBalancesAdapter` with `chain="hyperliquid"`).

## 4. CCTP Pre-Check

- [ ] Re-enable `CCTPBridgeAdapter` in `src/tq_oracle/adapters/check_adapters/__init__.py`.
- [ ] Validate CCTP config fields (token messenger address, hl/l1 subvault addresses) are surfaced and documented.
- [ ] Confirm `scripts/check_cctp_inflight.py` still works end-to-end.

## 5. Validation & Monitoring

- [ ] Re-run unit/integration tests covering Hyperliquid + CCTP (`tests/adapters/asset_adapters/test_hyperliquid.py`, `tests/adapters/check_adapters/test_cctp_bridge.py`, pipeline smoke tests).
- [ ] Execute manual dry-runs against staging vaults to verify NAV + pre-check behaviour.
