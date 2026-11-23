from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from autoexectool.actions.registry import default_action_registry
from autoexectool.app.container import build_container
from autoexectool.application.backup_service import BackupService
from autoexectool.connectors.registry import default_connector_registry
from autoexectool.domain.enums import OsType, ProtocolType
from autoexectool.domain.models import Host
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.loader import parse_playbook_dict
from autoexectool.storage.paths import resolve_data_paths


def test_sample_plugin_loaded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    assert "sample-echo" in container.loaded_plugins
    assert "sample.echo" in container.actions.types()
    assert "notify" in container.actions.types()


def test_notify_dry_run(tmp_path: Path) -> None:
    data = resolve_data_paths(tmp_path / "data")
    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=data,
        lock_hosts=False,
    )
    spec = parse_playbook_dict(
        {
            "name": "n",
            "stages": [
                {
                    "name": "m",
                    "steps": [
                        {
                            "id": "n1",
                            "action": "notify",
                            "url": "http://127.0.0.1:9/hook",
                            "message": "hi",
                        }
                    ],
                }
            ],
        }
    )
    host = Host(
        id="l",
        name="l",
        address="127.0.0.1",
        port=0,
        os_type=OsType.WINDOWS,
        protocol=ProtocolType.LOCAL,
    )
    plan = orch.dry_run(spec, host)
    assert any("notify" in x for x in plan)


def test_schedule_upsert_and_backup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    playbook = (
        Path(__file__).resolve().parents[1] / "templates" / "demos" / "group_demo.yaml"
    )
    sid = container.scheduler.upsert(
        name="t",
        mode="cron",
        cron="0 0 1 1 *",  # 每年一次，避免误触发
        playbook_path=str(playbook),
        enabled=True,
    )
    assert sid
    assert any(s.id == sid for s in container.scheduler.list_schedules())
    # 不应触发（距离上次触发点过远）
    fired = container.scheduler.tick_once(now=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert fired == []

    zip_path = BackupService(container).create_backup()
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"


def test_schedule_once_fires_and_disables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    playbook = (
        Path(__file__).resolve().parents[1] / "templates" / "demos" / "local_smoke.yaml"
    )
    if not playbook.exists():
        playbook = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "demos"
            / "local_smoke_windows.yaml"
        )
    local_tz = datetime.now().astimezone().tzinfo
    run_at = datetime(2026, 11, 23, 17, 30, tzinfo=local_tz)
    sid = container.scheduler.upsert(
        name="once",
        mode="once",
        run_at=run_at,
        playbook_path=str(playbook),
        enabled=True,
    )
    before = container.scheduler.tick_once(
        now=datetime(2026, 11, 23, 17, 0, tzinfo=local_tz)
    )
    assert before == []
    fired = container.scheduler.tick_once(
        now=datetime(2026, 11, 23, 17, 31, tzinfo=local_tz)
    )
    assert sid in fired
    rows = {r.id: r for r in container.scheduler.list_schedules()}
    assert rows[sid].enabled == 0
    assert rows[sid].last_run_at is not None
    # 已执行过的一次性任务不再触发
    assert (
        container.scheduler.tick_once(
            now=datetime(2026, 11, 23, 18, 0, tzinfo=local_tz)
        )
        == []
    )


def test_schedule_parallel_and_full_logs(tmp_path: Path, monkeypatch) -> None:
    """多条同时到期应并行触发，且写入与手动执行相同的会话/时间线日志。"""
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    playbook = (
        Path(__file__).resolve().parents[1] / "templates" / "demos" / "local_smoke.yaml"
    )
    if not playbook.exists():
        playbook = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "demos"
            / "local_smoke_windows.yaml"
        )
    local_tz = datetime.now().astimezone().tzinfo
    run_at = datetime(2026, 11, 23, 17, 30, tzinfo=local_tz)
    sid_a = container.scheduler.upsert(
        name="once-a",
        mode="once",
        run_at=run_at,
        playbook_path=str(playbook),
        enabled=True,
    )
    sid_b = container.scheduler.upsert(
        name="once-b",
        mode="once",
        run_at=run_at,
        playbook_path=str(playbook),
        enabled=True,
    )
    fired = container.scheduler.tick_once(
        now=datetime(2026, 11, 23, 17, 31, tzinfo=local_tz)
    )
    assert set(fired) == {sid_a, sid_b}

    from sqlalchemy import select

    from autoexectool.storage.models import ExecutionSessionRow

    with container.session_factory() as session:
        rows = list(session.scalars(select(ExecutionSessionRow)).all())
    sched_sessions = [r for r in rows if r.trigger == "schedule"]
    assert len(sched_sessions) >= 2
    for r in sched_sessions:
        timeline = container.paths.logs_exec / r.id / "timeline.jsonl"
        assert timeline.is_file(), f"缺少时间线日志：{timeline}"
        text = timeline.read_text(encoding="utf-8")
        assert "开始执行" in text or "session" in text
