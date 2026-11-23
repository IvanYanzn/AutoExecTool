from __future__ import annotations

from pathlib import Path

from autoexectool.actions.registry import default_action_registry
from autoexectool.app.container import build_container
from autoexectool.application.host_service import HostService
from autoexectool.connectors.registry import default_connector_registry
from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType, StepStatus
from autoexectool.domain.models import ActionResult, Host
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.loader import load_playbook_yaml, parse_playbook_dict
from autoexectool.orchestrator.masking import mask_secrets
from autoexectool.orchestrator.serialize import playbook_to_dict
from autoexectool.orchestrator.success import evaluate_success
from autoexectool.storage.paths import resolve_data_paths


def test_success_when_and_masking() -> None:
    ok = ActionResult(success=True, exit_code=0, stdout="hello world", message="ok")
    assert evaluate_success(ok, {"exit_code": 0, "stdout_contains": "hello"})
    assert not evaluate_success(ok, {"stdout_contains": "missing"})
    assert "******" in mask_secrets("password=secret123 token=abc")


def test_parallel_success_demo(tmp_path: Path) -> None:
    data = resolve_data_paths(tmp_path / "data")
    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=data,
        lock_hosts=False,
    )
    yaml_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "demos"
        / "parallel_success_demo.yaml"
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
    keys = {s.step_key for s in runtime.steps}
    assert "a" in keys and "b" in keys and "done" in keys
    assert all(s.status == StepStatus.SUCCEEDED for s in runtime.steps)


def test_host_group_crud(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    svc = HostService(container)
    h1 = svc.upsert_host(name="a", address="127.0.0.1", protocol="local", os_type="windows")
    h2 = svc.upsert_host(name="b", address="127.0.0.1", protocol="local", os_type="windows")
    g = svc.upsert_host_group(name="g1", host_ids=[h1.id, h2.id])
    assert len(g.host_ids) == 2
    hosts = svc.list_group_hosts(g.id)
    assert len(hosts) == 2
    targets = svc.resolve_hosts_with_credentials(group_id=g.id)
    assert len(targets) == 2
    svc.delete_host_group(g.id)
    assert all(x.id != g.id for x in svc.list_host_groups())


def test_serialize_roundtrip() -> None:
    spec = parse_playbook_dict(
        {
            "name": "t",
            "stages": [
                {
                    "name": "main",
                    "parallel": False,
                    "steps": [
                        {
                            "id": "s1",
                            "action": "shell.exec",
                            "command": "echo x",
                            "success_when": {"exit_code": 0},
                            "parallel_group": "p",
                        }
                    ],
                }
            ],
        }
    )
    data = playbook_to_dict(spec)
    again = parse_playbook_dict(data)
    assert again.stages[0].steps[0].success_when == {"exit_code": 0}
    assert again.stages[0].steps[0].parallel_group == "p"


def test_runtime_paths_dev() -> None:
    from autoexectool.runtime_paths import install_root, plugins_dir, templates_dir

    assert (install_root() / "pyproject.toml").exists() or (install_root() / "src").exists()
    assert templates_dir().is_dir()
    assert plugins_dir().is_dir()


def test_log_cleanup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    from autoexectool.application.log_cleanup import LogCleanupService

    old = container.paths.logs_exec / "old-session"
    old.mkdir(parents=True)
    (old / "x.out").write_text("hi", encoding="utf-8")
    # 将 mtime 调旧
    import os
    import time

    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    os.utime(old / "x.out", (past, past))
    result = LogCleanupService(container).cleanup(retain_days=30)
    assert result["dirs"] >= 1
    assert not old.exists()
