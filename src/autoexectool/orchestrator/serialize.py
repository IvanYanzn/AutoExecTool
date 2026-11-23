from __future__ import annotations

from typing import Any

from autoexectool.domain.models import PlaybookSpec, StepSpec


def step_to_dict(step: StepSpec) -> dict[str, Any]:
    data: dict[str, Any] = {"id": step.id, "action": step.action, **step.params}
    if step.host:
        data["host"] = step.host
    if step.use_playbook:
        data["use_playbook"] = step.use_playbook
    if step.playbook_vars:
        data["playbook_vars"] = step.playbook_vars
    if step.schedule:
        data["schedule"] = step.schedule
    if step.use_group:
        data["use_group"] = step.use_group
    if step.success_when:
        data["success_when"] = step.success_when
    if step.parallel_group:
        data["parallel_group"] = step.parallel_group
    if step.timeout_sec is not None:
        data["timeout_sec"] = step.timeout_sec
    if step.retries:
        data["retries"] = step.retries
    if step.retry_interval_sec != 3:
        data["retry_interval_sec"] = step.retry_interval_sec
    return data


def playbook_to_dict(spec: PlaybookSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "version": spec.version,
        "description": spec.description,
        "variables": spec.variables,
        "stages": [
            {
                "name": st.name,
                "parallel": st.parallel,
                "steps": [step_to_dict(s) for s in st.steps],
            }
            for st in spec.stages
        ],
        "on_failure": spec.on_failure,
        "command_groups": getattr(spec, "_inline_groups", {}) or {},
    }
