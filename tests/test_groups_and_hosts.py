from __future__ import annotations

from pathlib import Path

from autoexectool.actions.registry import default_action_registry
from autoexectool.app.container import build_container
from autoexectool.application.host_service import HostService
from autoexectool.connectors.registry import default_connector_registry
from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType
from autoexectool.domain.models import Host
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.loader import load_playbook_yaml
from autoexectool.storage.paths import resolve_data_paths


def test_expand_inline_group(tmp_path: Path) -> None:
    data = resolve_data_paths(tmp_path / "data")
    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=data,
        lock_hosts=False,
    )
    yaml_path = (
        Path(__file__).resolve().parents[1] / "templates" / "demos" / "group_demo.yaml"
    )
    spec = load_playbook_yaml(yaml_path)
    host = Host(
        id="local",
        name="local",
        address="127.0.0.1",
        port=0,
        os_type=OsType.WINDOWS,
        protocol=ProtocolType.LOCAL,
    )
    session_id = orch.start(spec, host)
    runtime = orch.get_status(session_id)
    assert runtime.status == ExecutionStatus.SUCCEEDED
    assert any("use_greet.say" in s.step_key or "say" in s.step_key for s in runtime.steps)


def test_host_crud(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    svc = HostService(container)
    host = svc.upsert_host(
        name="demo",
        address="127.0.0.1",
        protocol="local",
        os_type="windows",
    )
    assert host.id
    listed = svc.list_hosts()
    assert any(h.id == host.id for h in listed)
    msg = svc.test_connection(host.id)
    assert msg
    svc.delete_host(host.id)
    assert all(h.id != host.id for h in svc.list_hosts())
