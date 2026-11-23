from __future__ import annotations

from pathlib import Path

from autoexectool.actions.registry import default_action_registry
from autoexectool.connectors.registry import default_connector_registry
from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType
from autoexectool.domain.models import Host, PlaybookSpec, StageSpec, StepSpec
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.loader import parse_playbook_dict
from autoexectool.storage.paths import resolve_data_paths


def _local(host_id: str, name: str) -> Host:
    return Host(
        id=host_id,
        name=name,
        address="127.0.0.1",
        port=0,
        os_type=OsType.WINDOWS,
        protocol=ProtocolType.LOCAL,
    )


def test_parse_step_host() -> None:
    spec = parse_playbook_dict(
        {
            "name": "h",
            "stages": [
                {
                    "name": "main",
                    "steps": [
                        {
                            "id": "a",
                            "action": "delay",
                            "seconds": 0,
                            "host": "机房A",
                        }
                    ],
                }
            ],
        }
    )
    assert spec.stages[0].steps[0].host == "机房A"


def test_dry_run_shows_per_step_host(tmp_path: Path) -> None:
    hosts = {
        "alpha": _local("id-a", "alpha"),
        "beta": _local("id-b", "beta"),
    }

    def resolve(ref: str):
        return hosts[ref], None

    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=resolve_data_paths(tmp_path / "data"),
        resolve_host=resolve,
        lock_hosts=False,
    )
    spec = PlaybookSpec(
        name="multi",
        stages=[
            StageSpec(
                name="main",
                steps=[
                    StepSpec(id="on_a", action="delay", params={"seconds": 0}, host="alpha"),
                    StepSpec(id="on_b", action="delay", params={"seconds": 0}, host="beta"),
                ],
            )
        ],
    )
    plan = orch.dry_run(spec, hosts["alpha"])
    text = "\n".join(plan)
    assert "@alpha" in text
    assert "@beta" in text


def test_execute_switches_step_host(tmp_path: Path) -> None:
    default = _local("default", "default-local")
    other = _local("other", "other-local")
    seen: list[str] = []

    def resolve(ref: str):
        if ref == "other-local":
            return other, None
        raise AssertionError(ref)

    orch = Orchestrator(
        actions=default_action_registry(),
        connectors=default_connector_registry(),
        data_paths=resolve_data_paths(tmp_path / "data"),
        resolve_host=resolve,
        lock_hosts=False,
    )

    def on_step(rt):
        if rt.host_id:
            seen.append(rt.host_id)

    spec = PlaybookSpec(
        name="switch",
        stages=[
            StageSpec(
                name="main",
                steps=[
                    StepSpec(id="s1", action="delay", params={"seconds": 0}),
                    StepSpec(
                        id="s2",
                        action="delay",
                        params={"seconds": 0},
                        host="other-local",
                    ),
                ],
            )
        ],
    )
    sid = orch.start(spec, default, on_step=on_step)
    rt = orch.get_status(sid)
    assert rt.status == ExecutionStatus.SUCCEEDED
    assert rt.steps[0].host_id == "default"
    assert rt.steps[1].host_id == "other"
