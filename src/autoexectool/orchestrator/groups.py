from __future__ import annotations

from typing import Any, Callable

from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import PlaybookSpec, StageSpec, StepSpec

_GROUP_STEP_META = {
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
    "variables",
}


def expand_playbook_groups(
    playbook: PlaybookSpec,
    inline_groups: dict[str, Any] | None = None,
    resolve_group: Callable[[str], dict] | None = None,
) -> PlaybookSpec:
    """将 use_group 步骤展开为具体动作步骤。"""
    groups = dict(inline_groups or {})
    new_stages: list[StageSpec] = []
    for stage in playbook.stages:
        expanded: list[StepSpec] = []
        for step in stage.steps:
            if not step.use_group:
                expanded.append(step)
                continue
            name = step.use_group
            content = groups.get(name)
            if content is None and resolve_group is not None:
                content = resolve_group(name)
            if content is None:
                raise AppError(ErrorCode.VALIDATION_ERROR, f"未找到指令组：{name}")
            raw_steps = content.get("steps") if isinstance(content, dict) else None
            if not raw_steps:
                raise AppError(ErrorCode.VALIDATION_ERROR, f"指令组为空：{name}")
            for idx, raw in enumerate(raw_steps):
                action = raw.get("action")
                if not action:
                    raise AppError(ErrorCode.VALIDATION_ERROR, f"指令组 {name} 步骤缺少 action")
                params = {
                    k: v
                    for k, v in raw.items()
                    if k not in _GROUP_STEP_META
                }
                # 组级 schedule 仅作用于第一个展开步；host 默认继承引用步
                schedule = step.schedule if idx == 0 else raw.get("schedule")
                host_ref = raw.get("host") if raw.get("host") else step.host
                expanded.append(
                    StepSpec(
                        id=f"{step.id}.{raw.get('id') or action}",
                        action=str(action),
                        params=params,
                        schedule=schedule,
                        timeout_sec=raw.get("timeout_sec", step.timeout_sec),
                        retries=int(raw.get("retries") or step.retries or 0),
                        retry_interval_sec=int(
                            raw.get("retry_interval_sec") or step.retry_interval_sec or 3
                        ),
                        success_when=raw.get("success_when") or step.success_when,
                        parallel_group=raw.get("parallel_group") or step.parallel_group,
                        host=str(host_ref).strip() if host_ref else None,
                    )
                )
        new_stages.append(
            StageSpec(name=stage.name, steps=expanded, parallel=stage.parallel)
        )
    return PlaybookSpec(
        name=playbook.name,
        version=playbook.version,
        variables=playbook.variables,
        stages=new_stages,
        on_failure=playbook.on_failure,
        description=playbook.description,
    )
