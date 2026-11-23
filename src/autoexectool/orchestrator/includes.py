"""流程引用（use_playbook）：将子流程展开进父流程。

规则：
- 路径：绝对路径 → 相对父流程目录 → data/config/playbooks → templates
- 变量优先级：playbook_vars（引用步）> 父流程 variables > 子流程 variables
- 子流程阶段按顺序展平为当前阶段内的步骤，id 前缀为「引用步id.子阶段.子步骤id」
- 引用步的 host / schedule（仅首步）可继承到未单独指定的子步骤
- 禁止循环引用；默认最大嵌套 8 层
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import PlaybookSpec, StageSpec, StepSpec
from autoexectool.orchestrator.groups import expand_playbook_groups

MAX_INCLUDE_DEPTH = 8


def _search_named_file(root: Path, filename: str) -> Path | None:
    for p in root.glob("**/*"):
        if p.is_file() and p.name == filename:
            return p.resolve()
    return None


def resolve_playbook_path(
    ref: str,
    *,
    base_dir: Path,
    templates_dir: Path | None = None,
    playbooks_dir: Path | None = None,
) -> Path:
    text = (ref or "").strip()
    if not text:
        raise AppError(ErrorCode.VALIDATION_ERROR, "use_playbook 路径为空")
    candidate = Path(text)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()
    rel_base = (base_dir / text).resolve()
    if rel_base.exists():
        return rel_base

    search_roots: list[tuple[str, Path]] = []
    if playbooks_dir is not None:
        search_roots.append(("playbooks", playbooks_dir))
    if templates_dir is not None:
        search_roots.append(("templates", templates_dir))

    for _label, root in search_roots:
        rel = (root / text).resolve()
        if rel.exists():
            return rel
        # 允许只写文件名
        if text.replace("\\", "/") == Path(text).name:
            hit = _search_named_file(root, Path(text).name)
            if hit is not None:
                return hit

    tried = "、".join(
        [str(base_dir)] + [str(r) for _, r in search_roots]
    )
    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        f"未找到子流程：{text}（已查：绝对路径、{tried}）",
    )


def expand_playbook_includes(
    playbook: PlaybookSpec,
    *,
    base_dir: Path,
    templates_dir: Path | None = None,
    playbooks_dir: Path | None = None,
    resolve_group: Callable[[str], dict] | None = None,
    load_playbook: Callable[[Path], PlaybookSpec] | None = None,
    _stack: list[str] | None = None,
    _depth: int = 0,
) -> PlaybookSpec:
    """递归展开 use_playbook；返回无引用步的新 PlaybookSpec。"""
    from autoexectool.orchestrator.loader import load_playbook_yaml

    loader = load_playbook or load_playbook_yaml
    stack = list(_stack or [])
    if _depth > MAX_INCLUDE_DEPTH:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"流程引用嵌套超过 {MAX_INCLUDE_DEPTH} 层",
        )

    # 先合并本层已有 inline groups 展开之前，处理 include
    inline = getattr(playbook, "_inline_groups", {}) or {}
    # 继承子层展开痕迹，供时间线「引用」类别展示
    include_trace: list[dict[str, Any]] = list(
        getattr(playbook, "_include_trace", []) or []
    )
    merged_vars = dict(playbook.variables)
    new_stages: list[StageSpec] = []

    for stage in playbook.stages:
        expanded: list[StepSpec] = []
        for step in stage.steps:
            if not step.use_playbook:
                expanded.append(step)
                continue

            child_path = resolve_playbook_path(
                step.use_playbook,
                base_dir=base_dir,
                templates_dir=templates_dir,
                playbooks_dir=playbooks_dir,
            )
            key = str(child_path)
            if key in stack:
                chain = " → ".join(stack + [key])
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    f"检测到流程循环引用：{chain}",
                )

            child = loader(child_path)
            # 变量：子 < 父 < 引用步覆盖
            child_vars = dict(child.variables)
            child_vars.update(merged_vars)
            child_vars.update(step.playbook_vars or {})
            child.variables = child_vars
            setattr(child, "_inline_groups", getattr(child, "_inline_groups", {}) or {})

            child = expand_playbook_includes(
                child,
                base_dir=child_path.parent,
                templates_dir=templates_dir,
                playbooks_dir=playbooks_dir,
                resolve_group=resolve_group,
                load_playbook=loader,
                _stack=stack + [key],
                _depth=_depth + 1,
            )
            # 嵌套引用痕迹上浮
            include_trace.extend(getattr(child, "_include_trace", []) or [])
            child = expand_playbook_groups(
                child,
                inline_groups=getattr(child, "_inline_groups", {}) or {},
                resolve_group=resolve_group,
            )

            # 子流程变量回写父（不覆盖父已有键；引用步覆盖已在 child_vars 中）
            for k, v in child.variables.items():
                if k not in merged_vars:
                    merged_vars[k] = v
            merged_vars.update(step.playbook_vars or {})

            first = True
            flattened: list[StepSpec] = []
            for st in child.stages:
                for child_step in st.steps:
                    if child_step.use_playbook:
                        raise AppError(
                            ErrorCode.VALIDATION_ERROR,
                            f"子流程展开后仍含 use_playbook：{child_step.id}",
                        )
                    new_id = f"{step.id}.{st.name}.{child_step.id}"
                    # 清洗阶段名里不适合做 id 的字符
                    new_id = (
                        new_id.replace(" ", "_")
                        .replace("/", "_")
                        .replace("\\", "_")
                    )
                    host = child_step.host or step.host
                    schedule = step.schedule if first else child_step.schedule
                    first = False
                    flat = StepSpec(
                        id=new_id,
                        action=child_step.action,
                        params=dict(child_step.params),
                        schedule=schedule,
                        timeout_sec=child_step.timeout_sec
                        if child_step.timeout_sec is not None
                        else step.timeout_sec,
                        retries=child_step.retries,
                        retry_interval_sec=child_step.retry_interval_sec,
                        use_group=None,
                        success_when=child_step.success_when or step.success_when,
                        parallel_group=child_step.parallel_group
                        or step.parallel_group,
                        host=host,
                        use_playbook=None,
                        playbook_vars={},
                    )
                    flattened.append(flat)
                    expanded.append(flat)

            include_trace.append(
                {
                    "step_id": step.id,
                    "ref": step.use_playbook,
                    "path": str(child_path),
                    "child_name": child.name,
                    "stage": stage.name,
                    "depth": _depth,
                    "expanded_steps": len(flattened),
                    "prefix": f"{step.id}.",
                }
            )
        new_stages.append(
            StageSpec(name=stage.name, steps=expanded, parallel=stage.parallel)
        )

    out = PlaybookSpec(
        name=playbook.name,
        version=playbook.version,
        variables=merged_vars,
        stages=new_stages,
        on_failure=playbook.on_failure,
        description=playbook.description,
    )
    setattr(out, "_inline_groups", inline)
    setattr(out, "_include_trace", include_trace)
    return out
