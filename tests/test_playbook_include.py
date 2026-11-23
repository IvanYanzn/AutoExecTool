from __future__ import annotations

from pathlib import Path

from autoexectool.actions.registry import default_action_registry
from autoexectool.connectors.registry import default_connector_registry
from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType
from autoexectool.domain.errors import AppError
from autoexectool.domain.models import Host
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.includes import expand_playbook_includes, resolve_playbook_path
from autoexectool.orchestrator.loader import load_playbook_yaml, parse_playbook_dict
from autoexectool.storage.paths import resolve_data_paths


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_resolve_and_expand_include(tmp_path: Path) -> None:
    child = _write(
        tmp_path / "child.yaml",
        """
name: child
variables:
  X: from_child
  Y: child_only
stages:
  - name: c
    steps:
      - id: a
        action: delay
        seconds: 0
""",
    )
    parent = parse_playbook_dict(
        {
            "name": "parent",
            "variables": {"X": "from_parent"},
            "stages": [
                {
                    "name": "main",
                    "steps": [
                        {
                            "id": "inc",
                            "use_playbook": "child.yaml",
                            "playbook_vars": {"Z": "override"},
                        }
                    ],
                }
            ],
        }
    )
    expanded = expand_playbook_includes(
        parent, base_dir=tmp_path, templates_dir=tmp_path
    )
    assert len(expanded.stages[0].steps) == 1
    assert expanded.stages[0].steps[0].id == "inc.c.a"
    assert expanded.stages[0].steps[0].action == "delay"
    assert expanded.variables["X"] == "from_parent"
    assert expanded.variables["Y"] == "child_only"
    assert expanded.variables["Z"] == "override"
    assert resolve_playbook_path("child.yaml", base_dir=tmp_path) == child.resolve()
    trace = getattr(expanded, "_include_trace", []) or []
    assert len(trace) == 1
    assert trace[0]["ref"] == "child.yaml"
    assert trace[0]["expanded_steps"] == 1


def test_cycle_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / "a.yaml",
        """
name: a
stages:
  - name: main
    steps:
      - id: to_b
        use_playbook: b.yaml
""",
    )
    _write(
        tmp_path / "b.yaml",
        """
name: b
stages:
  - name: main
    steps:
      - id: to_a
        use_playbook: a.yaml
""",
    )
    spec = load_playbook_yaml(tmp_path / "a.yaml")
    try:
        expand_playbook_includes(spec, base_dir=tmp_path, templates_dir=tmp_path)
        raise AssertionError("expected cycle error")
    except AppError as exc:
        assert "循环" in exc.message


def test_include_executes(tmp_path: Path) -> None:
    _write(
        tmp_path / "leaf.yaml",
        """
name: leaf
stages:
  - name: s
    steps:
      - id: d
        action: delay
        seconds: 0
""",
    )
    root = _write(
        tmp_path / "root.yaml",
        """
name: root
stages:
  - name: main
    steps:
      - id: call
        use_playbook: leaf.yaml
""",
    )
    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=resolve_data_paths(tmp_path / "data"),
        lock_hosts=False,
    )
    host = Host(
        id="l",
        name="local",
        address="127.0.0.1",
        port=0,
        os_type=OsType.WINDOWS,
        protocol=ProtocolType.LOCAL,
    )
    sid = orch.start(load_playbook_yaml(root), host, playbook_path=str(root))
    rt = orch.get_status(sid)
    assert rt.status == ExecutionStatus.SUCCEEDED
    assert any(s.step_key.endswith(".d") or "call.s.d" in s.step_key for s in rt.steps)
