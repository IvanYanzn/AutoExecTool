from __future__ import annotations

import platform
from pathlib import Path

from autoexectool.actions.registry import default_action_registry
from autoexectool.connectors.registry import default_connector_registry
from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType
from autoexectool.domain.models import Host
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.loader import load_playbook_yaml
from autoexectool.storage.paths import resolve_data_paths


def test_local_smoke_playbook(tmp_path: Path) -> None:
    data = resolve_data_paths(tmp_path / "data")
    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=data,
    )
    root = Path(__file__).resolve().parents[1]
    demos = root / "templates" / "demos"
    if platform.system() == "Windows":
        yaml_path = demos / "local_smoke_windows.yaml"
        os_type = OsType.WINDOWS
    else:
        yaml_path = demos / "local_smoke.yaml"
        os_type = OsType.LINUX

    spec = load_playbook_yaml(yaml_path)
    host = Host(
        id="t1",
        name="local",
        address="127.0.0.1",
        port=0,
        os_type=os_type,
        protocol=ProtocolType.LOCAL,
    )
    session_id = orch.start(spec, host)
    runtime = orch.get_status(session_id)
    assert runtime.status == ExecutionStatus.SUCCEEDED
    assert len(runtime.steps) >= 2


def test_dry_run_plan(tmp_path: Path) -> None:
    data = resolve_data_paths(tmp_path / "data")
    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=data,
    )
    root = Path(__file__).resolve().parents[1]
    yaml_path = root / "templates" / "demos" / "local_smoke.yaml"
    spec = load_playbook_yaml(yaml_path)
    host = Host(
        id="t1",
        name="local",
        address="127.0.0.1",
        port=0,
        os_type=OsType.LINUX,
        protocol=ProtocolType.LOCAL,
    )
    plan = orch.dry_run(spec, host)
    assert any("echo_hello" in line or "shell.exec" in line for line in plan)
