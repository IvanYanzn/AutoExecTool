from __future__ import annotations

import json
from pathlib import Path

from autoexectool.app.container import build_container
from autoexectool.application.host_service import HostService
from autoexectool.application.session_service import SessionService
from autoexectool.domain.enums import ExecutionStatus
from autoexectool.orchestrator.loader import load_playbook_yaml


def test_session_persist_and_rerun(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    svc = HostService(container)
    host = svc.upsert_host(
        name="local",
        address="127.0.0.1",
        protocol="local",
        os_type="windows",
    )
    playbook_path = (
        Path(__file__).resolve().parents[1] / "templates" / "demos" / "group_demo.yaml"
    )
    spec = load_playbook_yaml(playbook_path)
    snapshot = {
        "name": spec.name,
        "version": spec.version,
        "variables": spec.variables,
        "stages": [
            {
                "name": st.name,
                "steps": [
                    {
                        "id": s.id,
                        "action": s.action,
                        **s.params,
                        **({"use_group": s.use_group} if s.use_group else {}),
                        **({"schedule": s.schedule} if s.schedule else {}),
                    }
                    for s in st.steps
                ],
            }
            for st in spec.stages
        ],
        "command_groups": getattr(spec, "_inline_groups", {}),
    }
    session_id = container.orchestrator.start(
        spec,
        host,
        playbook_path=str(playbook_path),
        playbook_json=json.dumps(snapshot, ensure_ascii=False),
    )
    runtime = container.orchestrator.get_status(session_id)
    assert runtime.status == ExecutionStatus.SUCCEEDED

    sessions = SessionService(container).list_sessions()
    assert any(s.id == session_id for s in sessions)

    new_id = SessionService(container).rerun(session_id, from_failed_step=False)
    assert container.orchestrator.get_status(new_id).status == ExecutionStatus.SUCCEEDED


def test_mark_interrupted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    store = container.orchestrator.session_store
    assert store is not None
    store.create_session(session_id="running-1", playbook_name="x")
    n = store.mark_interrupted_running()
    assert n >= 1
    row = store.get_session("running-1")
    assert row is not None
    assert row.status == ExecutionStatus.INTERRUPTED.value


def test_host_csv_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    svc = HostService(container)
    svc.upsert_host(name="h1", address="10.0.0.1", protocol="ssh", os_type="linux", port=22)
    csv_path = tmp_path / "hosts.csv"
    assert svc.export_csv(csv_path) >= 1
    # 再导入到新库
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data2"))
    container2 = build_container(tmp_path / "data2")
    n = HostService(container2).import_csv(csv_path)
    assert n >= 1
    assert any(h.name == "h1" for h in HostService(container2).list_hosts())
