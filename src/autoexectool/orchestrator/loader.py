from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import PlaybookSpec, StageSpec, StepSpec

STEP_META = {
    "id",
    "action",
    "schedule",
    "timeout_sec",
    "retries",
    "retry_interval_sec",
    "use_group",
    "success_when",
    "parallel_group",
    "host",
    "use_playbook",
    "playbook_vars",
    "variables",  # 引用子流程时的变量覆盖别名
}
_STEP_META = STEP_META  # 兼容旧引用


def load_playbook_yaml(source: str | Path) -> PlaybookSpec:
    path = Path(source)
    if not path.exists():
        raise AppError(ErrorCode.VALIDATION_ERROR, f"流程文件不存在：{path}")
    text = path.read_text(encoding="utf-8")
    return parse_playbook_dict(yaml.safe_load(text) or {})


def parse_playbook_dict(data: dict[str, Any]) -> PlaybookSpec:
    if not isinstance(data, dict) or "name" not in data:
        raise AppError(ErrorCode.VALIDATION_ERROR, "流程 YAML 缺少 name")
    stages: list[StageSpec] = []
    raw_stages = data.get("stages") or []
    if not raw_stages and data.get("steps"):
        raw_stages = [{"name": "main", "steps": data["steps"]}]
    for stage in raw_stages:
        steps = []
        for step in stage.get("steps") or []:
            action = step.get("action") or (
                "group"
                if step.get("use_group")
                else ("playbook" if step.get("use_playbook") else None)
            )
            if not action and not step.get("use_group") and not step.get("use_playbook"):
                raise AppError(ErrorCode.VALIDATION_ERROR, f"步骤缺少 action：{step}")
            params = {k: v for k, v in step.items() if k not in _STEP_META}
            host_ref = step.get("host")
            pb_vars = step.get("playbook_vars") or step.get("variables") or {}
            if not isinstance(pb_vars, dict):
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    f"步骤 {step.get('id')} 的 playbook_vars/variables 须为字典",
                )
            use_pb = step.get("use_playbook")
            steps.append(
                StepSpec(
                    id=str(step.get("id") or step.get("action") or "step"),
                    action=str(action or "group"),
                    params=params,
                    schedule=step.get("schedule"),
                    timeout_sec=step.get("timeout_sec"),
                    retries=int(step.get("retries") or 0),
                    retry_interval_sec=int(step.get("retry_interval_sec") or 3),
                    use_group=step.get("use_group"),
                    success_when=step.get("success_when"),
                    parallel_group=step.get("parallel_group"),
                    host=str(host_ref).strip() if host_ref else None,
                    use_playbook=str(use_pb).strip() if use_pb else None,
                    playbook_vars=dict(pb_vars),
                )
            )
        stages.append(
            StageSpec(
                name=str(stage.get("name") or "stage"),
                steps=steps,
                parallel=bool(stage.get("parallel")),
            )
        )
    spec = PlaybookSpec(
        name=str(data["name"]),
        version=int(data.get("version") or 1),
        variables=dict(data.get("variables") or {}),
        stages=stages,
        on_failure=dict(data.get("on_failure") or {}),
        description=str(data.get("description") or ""),
    )
    setattr(spec, "_inline_groups", dict(data.get("command_groups") or {}))
    return spec
