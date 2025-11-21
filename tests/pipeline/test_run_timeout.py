import asyncio
import logging

import pytest

from tq_oracle.pipeline import run as pipeline_run
from tq_oracle.settings import OracleSettings
from tq_oracle.state import AppState


@pytest.mark.asyncio
async def test_run_report_completes_within_timeout(monkeypatch):
    calls: list[str] = []

    async def fast_discover(_state: AppState) -> str:
        await asyncio.sleep(0)
        return "0xBASE"

    def stage(name: str):
        async def _inner(ctx):  # type: ignore[unused-arg]
            calls.append(name)
            await asyncio.sleep(0.01)

        return _inner

    monkeypatch.setattr(pipeline_run, "_discover_base_asset", fast_discover)
    monkeypatch.setattr(pipeline_run, "run_preflight", stage("preflight"))
    monkeypatch.setattr(pipeline_run, "collect_assets", stage("collect"))
    monkeypatch.setattr(pipeline_run, "price_assets", stage("price"))
    monkeypatch.setattr(pipeline_run, "build_report", stage("build"))
    monkeypatch.setattr(pipeline_run, "publish_report", stage("publish"))

    settings = OracleSettings(global_timeout_seconds=0.2)
    state = AppState(settings=settings, logger=logging.getLogger("test"))

    await pipeline_run.run_report(state, "0xV")

    assert calls == ["preflight", "collect", "price", "build", "publish"]


@pytest.mark.asyncio
async def test_run_report_raises_timeout(monkeypatch):
    async def slow_discover(_state: AppState) -> str:
        await asyncio.sleep(0.2)
        return "0xBASE"

    async def noop(ctx):  # type: ignore[unused-arg]
        await asyncio.sleep(0)

    monkeypatch.setattr(pipeline_run, "_discover_base_asset", slow_discover)
    monkeypatch.setattr(pipeline_run, "run_preflight", noop)
    monkeypatch.setattr(pipeline_run, "collect_assets", noop)
    monkeypatch.setattr(pipeline_run, "price_assets", noop)
    monkeypatch.setattr(pipeline_run, "build_report", noop)
    monkeypatch.setattr(pipeline_run, "publish_report", noop)

    settings = OracleSettings(global_timeout_seconds=0.05)
    state = AppState(settings=settings, logger=logging.getLogger("test"))

    with pytest.raises(asyncio.TimeoutError):
        await pipeline_run.run_report(state, "0xV")
