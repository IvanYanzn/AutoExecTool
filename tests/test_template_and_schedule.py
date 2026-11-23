from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from autoexectool.orchestrator.schedule import compute_wait_seconds, resolve_execute_at
from autoexectool.orchestrator.template import render_value


def test_render_host_address() -> None:
    text = render_value("http://{{host.address}}:8080/health", {"host.address": "10.0.0.1"})
    assert text == "http://10.0.0.1:8080/health"


def test_resolve_hhmm_today() -> None:
    now = datetime(2026, 11, 19, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    target = resolve_execute_at("22:30", timezone="Asia/Shanghai", now=now)
    assert target.hour == 22
    assert target.minute == 30


def test_if_past_run_immediately() -> None:
    now = datetime(2026, 11, 19, 23, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    wait, _reason = compute_wait_seconds(
        {"execute_at": "22:30", "timezone": "Asia/Shanghai", "if_past": "run_immediately"},
        now=now,
    )
    assert wait == 0.0
