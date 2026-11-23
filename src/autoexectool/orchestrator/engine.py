from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from autoexectool.actions.base import ExecutionContext
from autoexectool.actions.registry import ActionRegistry
from autoexectool.connectors.base import RemoteSession
from autoexectool.connectors.registry import ConnectorRegistry
from autoexectool.domain.enums import ExecutionStatus, StepStatus
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import (
    Credential,
    Host,
    PlaybookSpec,
    SessionRuntime,
    StepRuntime,
    StepSpec,
)
from autoexectool.logging.setup import get_logger
from autoexectool.orchestrator.groups import expand_playbook_groups
from autoexectool.orchestrator.host_lock import GLOBAL_HOST_LOCKS
from autoexectool.orchestrator.includes import expand_playbook_includes
from autoexectool.orchestrator.masking import mask_secrets
from autoexectool.orchestrator.schedule import compute_wait_seconds
from autoexectool.orchestrator.session_store import SessionStore
from autoexectool.orchestrator.success import evaluate_success
from autoexectool.orchestrator.template import render_params, render_value
from autoexectool.orchestrator.timeline import (
    TimelineWriter,
    preview_text,
    summarize_exec,
)
from autoexectool.runtime_paths import playbooks_dir, templates_dir
from autoexectool.storage.paths import DataPaths

logger = get_logger("orchestrator")

ResolveHostFn = Callable[[str], tuple[Host, Credential | None]]


class _SessionConnections:
    """会话内按主机缓存连接；步骤可切换不同库存主机。"""

    def __init__(self, connectors: ConnectorRegistry) -> None:
        self._connectors = connectors
        self._lock = threading.Lock()
        self._by_host: dict[str, tuple[Any, Any]] = {}

    def get(
        self,
        host: Host,
        credential: Credential | None,
        *,
        dry_run: bool,
    ) -> tuple[Any, Any]:
        if dry_run:
            connector = self._connectors.get(host.protocol.value)
            return connector, RemoteSession(host=host, handle=None)
        with self._lock:
            cached = self._by_host.get(host.id)
            if cached is not None:
                return cached
            connector = self._connectors.get(host.protocol.value)
            remote = connector.connect(host, credential)
            self._by_host[host.id] = (connector, remote)
            return connector, remote

    def remotes(self) -> list[Any]:
        with self._lock:
            return [remote for _, remote in self._by_host.values()]

    def disconnect_all(self) -> None:
        with self._lock:
            items = list(self._by_host.values())
            self._by_host.clear()
        for connector, remote in items:
            try:
                connector.disconnect(remote)
            except Exception:  # noqa: BLE001
                logger.exception("disconnect failed")


class Orchestrator:
    def __init__(
        self,
        *,
        actions: ActionRegistry,
        connectors: ConnectorRegistry,
        data_paths: DataPaths,
        resolve_group: Callable[[str], dict] | None = None,
        resolve_host: ResolveHostFn | None = None,
        lock_hosts: bool = True,
        session_store: SessionStore | None = None,
    ) -> None:
        self.actions = actions
        self.connectors = connectors
        self.data_paths = data_paths
        self.resolve_group = resolve_group
        self.resolve_host = resolve_host
        self.lock_hosts = lock_hosts
        self.session_store = session_store
        self._cancel_flags: dict[str, threading.Event] = {}
        self._sessions: dict[str, SessionRuntime] = {}
        self._session_conns: dict[str, _SessionConnections] = {}
        self._runtime_lock = threading.Lock()

    def _prepare(
        self, playbook: PlaybookSpec, *, playbook_path: str = ""
    ) -> PlaybookSpec:
        inline = getattr(playbook, "_inline_groups", {}) or {}
        base = (
            Path(playbook_path).resolve().parent
            if playbook_path
            else playbooks_dir()
        )
        expanded = expand_playbook_includes(
            playbook,
            base_dir=base,
            templates_dir=templates_dir(),
            playbooks_dir=playbooks_dir(),
            resolve_group=self.resolve_group,
        )
        inline = getattr(expanded, "_inline_groups", {}) or inline
        return expand_playbook_groups(
            expanded,
            inline_groups=inline,
            resolve_group=self.resolve_group,
        )

    def get_status(self, session_id: str) -> SessionRuntime:
        if session_id not in self._sessions:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"会话不存在：{session_id}")
        return self._sessions[session_id]

    def cancel(self, session_id: str) -> None:
        flag = self._cancel_flags.get(session_id)
        if flag:
            flag.set()
        conns = self._session_conns.get(session_id)
        if conns is None:
            return
        for remote in conns.remotes():
            if remote is not None and isinstance(remote.handle, dict):
                proc = remote.handle.get("proc")
                if proc is not None:
                    try:
                        from autoexectool.connectors.local import _kill_process_tree

                        _kill_process_tree(proc)
                    except Exception:  # noqa: BLE001
                        logger.exception("kill local process on cancel failed")

    def dry_run(
        self,
        playbook: PlaybookSpec,
        host: Host,
        credential: Credential | None = None,
        variables: dict[str, Any] | None = None,
        *,
        playbook_path: str = "",
    ) -> list[str]:
        playbook = self._prepare(playbook, playbook_path=playbook_path)
        plan: list[str] = []
        vars_map = self._build_vars(playbook, host, variables)
        plan.append(f"默认目标：{host.name} ({host.protocol.value})")
        for inc in getattr(playbook, "_include_trace", []) or []:
            plan.append(
                f"引用：[{inc.get('step_id')}] {inc.get('ref')} "
                f"→ {inc.get('path')}（展开 {inc.get('expanded_steps', 0)} 步）"
            )
        for stage in playbook.stages:
            mode = "并行" if stage.parallel else "串行"
            plan.append(f"阶段：{stage.name}（{mode}）")
            for step in stage.steps:
                step_host, _cred = self._resolve_step_target(
                    step, default_host=host, default_cred=credential, variables=vars_map
                )
                self._apply_host_vars(vars_map, step_host)
                params = render_params(step.params, vars_map)
                self._check_os(step_host, step.action)
                where = f"@{step_host.name}"
                plan.append(f"  - [{step.id}] {where} {step.action} {params}")
                handler = self.actions.get(step.action)
                handler.validate(params)
        return plan

    def start(
        self,
        playbook: PlaybookSpec,
        host: Host,
        credential: Credential | None = None,
        variables: dict[str, Any] | None = None,
        *,
        dry_run: bool = False,
        on_step: Callable[[StepRuntime], None] | None = None,
        on_session: Callable[[str], None] | None = None,
        playbook_path: str = "",
        playbook_json: str = "",
        start_from_step: str | None = None,
        trigger: str = "manual",
    ) -> str:
        playbook = self._prepare(playbook, playbook_path=playbook_path)
        lock_ids = self._collect_lock_host_ids(
            playbook, host, credential, variables
        )
        if self.lock_hosts and not dry_run and lock_ids:
            with GLOBAL_HOST_LOCKS.acquire_many(lock_ids, blocking=False):
                return self._start_unlocked(
                    playbook,
                    host,
                    credential,
                    variables,
                    dry_run=dry_run,
                    on_step=on_step,
                    on_session=on_session,
                    playbook_path=playbook_path,
                    playbook_json=playbook_json,
                    start_from_step=start_from_step,
                    trigger=trigger,
                )
        return self._start_unlocked(
            playbook,
            host,
            credential,
            variables,
            dry_run=dry_run,
            on_step=on_step,
            on_session=on_session,
            playbook_path=playbook_path,
            playbook_json=playbook_json,
            start_from_step=start_from_step,
            trigger=trigger,
        )

    def start_on_hosts(
        self,
        playbook: PlaybookSpec,
        hosts: list[tuple[Host, Credential | None]],
        variables: dict[str, Any] | None = None,
        *,
        playbook_path: str = "",
        playbook_json: str = "",
        max_parallel: int = 5,
    ) -> list[str]:
        """对主机列表执行同一流程，返回 session id 列表。"""
        ids: list[str] = []
        if len(hosts) == 1:
            host, cred = hosts[0]
            ids.append(
                self.start(
                    playbook,
                    host,
                    cred,
                    variables,
                    playbook_path=playbook_path,
                    playbook_json=playbook_json,
                )
            )
            return ids

        def _one(item: tuple[Host, Credential | None]) -> str:
            h, c = item
            return self.start(
                playbook,
                h,
                c,
                variables,
                playbook_path=playbook_path,
                playbook_json=playbook_json,
            )

        with ThreadPoolExecutor(max_workers=max(1, max_parallel)) as pool:
            futs = [pool.submit(_one, item) for item in hosts]
            for fut in as_completed(futs):
                ids.append(fut.result())
        return ids

    def _persist_runtime(self, runtime: SessionRuntime, *, dry_run: bool) -> None:
        if dry_run or not self.session_store:
            return
        try:
            self.session_store.sync_runtime(runtime)
        except Exception:  # noqa: BLE001
            logger.exception("persist session failed")

    def _start_unlocked(
        self,
        playbook: PlaybookSpec,
        host: Host,
        credential: Credential | None = None,
        variables: dict[str, Any] | None = None,
        *,
        dry_run: bool = False,
        on_step: Callable[[StepRuntime], None] | None = None,
        on_session: Callable[[str], None] | None = None,
        playbook_path: str = "",
        playbook_json: str = "",
        start_from_step: str | None = None,
        trigger: str = "manual",
    ) -> str:
        session_id = str(uuid.uuid4())
        runtime = SessionRuntime(
            id=session_id,
            playbook_name=playbook.name,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            variables=self._build_vars(playbook, host, variables),
        )
        self._sessions[session_id] = runtime
        cancel = threading.Event()
        self._cancel_flags[session_id] = cancel
        log_dir = self.data_paths.logs_exec / session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        timeline = TimelineWriter(log_dir / "timeline.jsonl")
        conns = _SessionConnections(self.connectors)
        self._session_conns[session_id] = conns

        if self.session_store and not dry_run:
            self.session_store.create_session(
                session_id=session_id,
                playbook_name=playbook.name,
                playbook_path=playbook_path,
                playbook_json=playbook_json,
                host_id=host.id,
                variables=variables or {},
                trigger=trigger,
            )

        timeline.emit(
            "session",
            f"开始执行「{playbook.name}」→ 默认主机 {host.name} ({host.protocol.value})",
            level="info",
            data={
                "session_id": session_id,
                "playbook": playbook.name,
                "playbook_path": playbook_path,
                "host_id": host.id,
                "host_name": host.name,
                "trigger": trigger,
            },
        )
        for inc in getattr(playbook, "_include_trace", []) or []:
            timeline.emit(
                "include",
                (
                    f"引用子流程「{inc.get('child_name') or inc.get('ref')}」"
                    f"（{inc.get('ref')}）→ {inc.get('path')}；"
                    f"展开 {inc.get('expanded_steps', 0)} 步，"
                    f"步骤前缀 {inc.get('prefix')}"
                ),
                level="info",
                stage=str(inc.get("stage") or ""),
                step=str(inc.get("step_id") or ""),
                data=dict(inc),
            )
        if on_session:
            try:
                on_session(session_id)
            except Exception:  # noqa: BLE001
                logger.exception("on_session callback failed")

        skipping = bool(start_from_step)
        try:
            for stage in playbook.stages:
                mode = "并行" if stage.parallel else "串行"
                timeline.emit(
                    "stage",
                    f"进入阶段「{stage.name}」（{mode}）",
                    level="info",
                    stage=stage.name,
                )
                pending: list[StepSpec] = []
                for step in stage.steps:
                    if skipping:
                        if step.id == start_from_step:
                            skipping = False
                        else:
                            skipped = StepRuntime(
                                step_key=step.id,
                                action=step.action,
                                host_id=host.id,
                                status=StepStatus.SKIPPED,
                                message="重跑时跳过（失败步之前）",
                                started_at=datetime.now(timezone.utc),
                                ended_at=datetime.now(timezone.utc),
                            )
                            runtime.steps.append(skipped)
                            timeline.emit(
                                "node",
                                "跳过",
                                level="warn",
                                stage=stage.name,
                                step=step.id,
                                action=step.action,
                            )
                            continue
                    pending.append(step)

                batches = self._batch_steps(pending, force_parallel=stage.parallel)
                for batch in batches:
                    if cancel.is_set():
                        runtime.status = ExecutionStatus.CANCELLED
                        raise AppError(ErrorCode.CANCELLED)
                    if len(batch) == 1:
                        self._execute_step(
                            batch[0],
                            default_host=host,
                            default_cred=credential,
                            conns=conns,
                            runtime=runtime,
                            log_dir=log_dir,
                            timeline=timeline,
                            stage_name=stage.name,
                            dry_run=dry_run,
                            cancel=cancel,
                            on_step=on_step,
                        )
                    else:
                        errors: list[Exception] = []

                        def _run(step: StepSpec) -> None:
                            try:
                                self._execute_step(
                                    step,
                                    default_host=host,
                                    default_cred=credential,
                                    conns=conns,
                                    runtime=runtime,
                                    log_dir=log_dir,
                                    timeline=timeline,
                                    stage_name=stage.name,
                                    dry_run=dry_run,
                                    cancel=cancel,
                                    on_step=on_step,
                                )
                            except Exception as exc:  # noqa: BLE001
                                errors.append(exc)

                        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                            list(pool.map(_run, batch))
                        if errors:
                            runtime.status = ExecutionStatus.FAILED
                            runtime.summary = str(errors[0])
                            raise errors[0]

                timeline.emit(
                    "stage",
                    f"阶段「{stage.name}」完成",
                    level="ok",
                    stage=stage.name,
                )

            runtime.status = ExecutionStatus.SUCCEEDED
            runtime.summary = "全部步骤成功"
            self._maybe_notify(playbook, runtime, ok=True)
        except AppError as exc:
            if exc.code == ErrorCode.CANCELLED:
                runtime.status = ExecutionStatus.CANCELLED
            elif runtime.status != ExecutionStatus.FAILED:
                runtime.status = ExecutionStatus.FAILED
            runtime.summary = exc.message
            timeline.emit("error", exc.message, level="fail")
            logger.exception("session %s failed: %s", session_id, exc)
            self._maybe_notify(playbook, runtime, ok=False)
        except Exception as exc:  # noqa: BLE001
            runtime.status = ExecutionStatus.FAILED
            runtime.summary = str(exc)
            timeline.emit("error", str(exc), level="fail")
            logger.exception("session %s error", session_id)
            self._maybe_notify(playbook, runtime, ok=False)
        finally:
            conns.disconnect_all()
            self._session_conns.pop(session_id, None)
            runtime.ended_at = datetime.now(timezone.utc)
            end_level = (
                "ok"
                if runtime.status == ExecutionStatus.SUCCEEDED
                else (
                    "warn"
                    if runtime.status == ExecutionStatus.CANCELLED
                    else "fail"
                )
            )
            summary_text = self._format_session_summary(
                runtime, playbook_name=playbook.name, default_host=host
            )
            timeline.emit(
                "session",
                f"结束：{runtime.status} | {runtime.summary}",
                level=end_level,
                data={"status": str(runtime.status)},
            )
            timeline.emit(
                "session",
                summary_text,
                level=end_level,
                data={
                    "status": str(runtime.status),
                    "kind": "result_summary",
                    "started_at": runtime.started_at.isoformat()
                    if runtime.started_at
                    else "",
                    "ended_at": runtime.ended_at.isoformat()
                    if runtime.ended_at
                    else "",
                    "duration_sec": self._duration_seconds(
                        runtime.started_at, runtime.ended_at
                    ),
                },
            )
            meta = log_dir / "meta.txt"
            meta.write_text(
                f"status={runtime.status}\nsummary={runtime.summary}\n\n{summary_text}\n",
                encoding="utf-8",
            )
            self._persist_runtime(runtime, dry_run=dry_run)
        return session_id

    def _execute_step(
        self,
        step: StepSpec,
        *,
        default_host: Host,
        default_cred: Credential | None,
        conns: _SessionConnections,
        runtime: SessionRuntime,
        log_dir: Path,
        timeline: TimelineWriter,
        stage_name: str = "",
        dry_run: bool,
        cancel: threading.Event,
        on_step: Callable[[StepRuntime], None] | None,
    ) -> None:
        if cancel.is_set():
            raise AppError(ErrorCode.CANCELLED)

        step_host, step_cred = self._resolve_step_target(
            step,
            default_host=default_host,
            default_cred=default_cred,
            variables=runtime.variables,
        )
        self._apply_host_vars(runtime.variables, step_host)

        step_rt = StepRuntime(
            step_key=step.id,
            action=step.action,
            host_id=step_host.id,
            status=StepStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )
        with self._runtime_lock:
            runtime.steps.append(step_rt)

        host_label = f"{step_host.name} ({step_host.protocol.value})"
        timeline.emit(
            "node",
            f"就绪 → {host_label}",
            level="info",
            stage=stage_name,
            step=step.id,
            action=step.action,
            data={
                "host_id": step_host.id,
                "host_name": step_host.name,
                "host_ref": step.host or "",
            },
        )
        if on_step:
            on_step(step_rt)
        self._persist_runtime(runtime, dry_run=dry_run)

        if step.schedule:
            wait_sec, reason = compute_wait_seconds(step.schedule)
            if wait_sec < 0:
                step_rt.status = StepStatus.SKIPPED
                step_rt.message = reason
                step_rt.ended_at = datetime.now(timezone.utc)
                timeline.emit(
                    "node",
                    reason,
                    level="warn",
                    stage=stage_name,
                    step=step.id,
                    action=step.action,
                )
                self._persist_runtime(runtime, dry_run=dry_run)
                return
            if wait_sec > 0:
                step_rt.status = StepStatus.WAITING_UNTIL
                step_rt.message = reason
                timeline.emit(
                    "node",
                    reason,
                    level="warn",
                    stage=stage_name,
                    step=step.id,
                    action=step.action,
                )
                if on_step:
                    on_step(step_rt)
                self._persist_runtime(runtime, dry_run=dry_run)
                self._sleep_cancellable(wait_sec, cancel)

        self._check_os(step_host, step.action)
        handler = self.actions.get(step.action)
        params = render_params(step.params, runtime.variables)
        params = render_params(params, runtime.variables)
        handler.validate(params)

        if step.timeout_sec is not None and params.get("timeout") is None:
            params["timeout"] = float(step.timeout_sec)

        exec_summary = summarize_exec(step.action, params)
        timeline.emit(
            "exec",
            f"[{host_label}] {exec_summary}",
            level="info",
            stage=stage_name,
            step=step.id,
            action=step.action,
            data={"host_id": step_host.id, "host_name": step_host.name},
        )

        try:
            connector, remote = conns.get(step_host, step_cred, dry_run=dry_run)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCode.HOST_UNREACHABLE,
                f"连接主机「{step_host.name}」失败：{exc}",
            ) from exc

        if not dry_run and step.host:
            timeline.emit(
                "meta",
                f"步骤使用主机：{host_label} / {step_host.address}",
                level="info",
                stage=stage_name,
                step=step.id,
                action=step.action,
            )

        ctx = ExecutionContext(
            host=step_host,
            connector=connector,
            session=remote,
            variables=runtime.variables,
            dry_run=dry_run,
            cancel=cancel,
        )

        step_rt.status = StepStatus.RUNNING
        step_rt.message = "执行中…"
        timeline.emit(
            "node",
            f"执行中… → {host_label}",
            level="warn",
            stage=stage_name,
            step=step.id,
            action=step.action,
        )
        if on_step:
            on_step(step_rt)
        self._persist_runtime(runtime, dry_run=dry_run)

        attempts = max(1, step.retries + 1)
        last_error: Exception | None = None
        result = None
        for attempt in range(attempts):
            if cancel.is_set():
                raise AppError(ErrorCode.CANCELLED)
            if attempt > 0:
                timeline.emit(
                    "meta",
                    f"重试第 {attempt + 1}/{attempts} 次",
                    level="warn",
                    stage=stage_name,
                    step=step.id,
                    action=step.action,
                )
            try:
                result = handler.execute(ctx, params)
                ok = evaluate_success(result, step.success_when)
                if ok:
                    result.success = True
                    break
                result.success = False
                last_error = AppError(
                    ErrorCode.STEP_FAILED,
                    result.message or "成功条件未满足",
                    detail=mask_secrets(result.stderr or result.stdout),
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt < attempts - 1:
                time.sleep(step.retry_interval_sec)

        out_path = log_dir / f"{step.id}.out"
        err_path = log_dir / f"{step.id}.err"
        if result:
            # 只落盘真实管道输出，不用 result.message 顶替（否则空 stdout 会变成「cmd 执行完成」）
            stdout_masked = mask_secrets(result.stdout or "")
            stderr_masked = mask_secrets(result.stderr or "")
            out_path.write_text(stdout_masked, encoding="utf-8")
            err_path.write_text(stderr_masked, encoding="utf-8")
            step_rt.log_path = str(out_path)
            step_rt.exit_code = result.exit_code
            step_rt.message = mask_secrets(result.message)
            if result.outputs:
                for k, v in result.outputs.items():
                    runtime.variables[f"steps.{step.id}.{k}"] = v
                    runtime.variables[k] = v

            ret_level = "ok" if result.success else "fail"
            timeline.emit(
                "return",
                f"exit_code={result.exit_code} | {step_rt.message}",
                level=ret_level,
                stage=stage_name,
                step=step.id,
                action=step.action,
                data={
                    "exit_code": result.exit_code,
                    "success": result.success,
                    "host_id": step_host.id,
                },
            )
            out_preview = preview_text(stdout_masked)
            if out_preview:
                timeline.emit(
                    "output",
                    out_preview,
                    level=ret_level,
                    stage=stage_name,
                    step=step.id,
                    action=step.action,
                    data={"stream": "stdout", "path": str(out_path)},
                )
            err_preview = preview_text(stderr_masked)
            if err_preview:
                timeline.emit(
                    "output",
                    err_preview,
                    level="fail" if not result.success else "warn",
                    stage=stage_name,
                    step=step.id,
                    action=step.action,
                    data={"stream": "stderr", "path": str(err_path)},
                )

            if result.success:
                step_rt.status = StepStatus.SUCCEEDED
            else:
                step_rt.status = StepStatus.FAILED
                step_rt.ended_at = datetime.now(timezone.utc)
                runtime.status = ExecutionStatus.FAILED
                runtime.summary = step_rt.message
                dur = self._duration_seconds(step_rt.started_at, step_rt.ended_at)
                timeline.emit(
                    "node",
                    f"失败：{step_rt.message}｜耗时 {self._format_duration(dur)}",
                    level="fail",
                    stage=stage_name,
                    step=step.id,
                    action=step.action,
                    data={"duration_sec": dur, "host_id": step_host.id},
                )
                self._persist_runtime(runtime, dry_run=dry_run)
                raise last_error or AppError(ErrorCode.STEP_FAILED, step_rt.message)
        elif last_error:
            step_rt.status = StepStatus.FAILED
            step_rt.ended_at = datetime.now(timezone.utc)
            step_rt.message = mask_secrets(str(last_error))
            runtime.status = ExecutionStatus.FAILED
            dur = self._duration_seconds(step_rt.started_at, step_rt.ended_at)
            timeline.emit(
                "error",
                f"{step_rt.message}｜耗时 {self._format_duration(dur)}",
                level="fail",
                stage=stage_name,
                step=step.id,
                action=step.action,
                data={"duration_sec": dur},
            )
            self._persist_runtime(runtime, dry_run=dry_run)
            raise last_error

        step_rt.ended_at = datetime.now(timezone.utc)
        dur = self._duration_seconds(step_rt.started_at, step_rt.ended_at)
        timeline.emit(
            "node",
            f"成功 → {host_label}｜耗时 {self._format_duration(dur)}",
            level="ok",
            stage=stage_name,
            step=step.id,
            action=step.action,
            data={
                "duration_sec": dur,
                "host_id": step_host.id,
                "host_name": step_host.name,
            },
        )
        if on_step:
            on_step(step_rt)
        self._persist_runtime(runtime, dry_run=dry_run)

    def _resolve_step_target(
        self,
        step: StepSpec,
        *,
        default_host: Host,
        default_cred: Credential | None,
        variables: dict[str, Any],
    ) -> tuple[Host, Credential | None]:
        raw = (step.host or "").strip()
        if not raw:
            return default_host, default_cred
        rendered = str(render_value(raw, variables)).strip()
        if not rendered or rendered == raw and "{{" in raw:
            # 未解析的模板保留原样再尝试；若仍是 {{x}} 则报错
            if "{{" in rendered:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    f"步骤 {step.id} 的 host 未能解析：{raw}",
                )
        if rendered.lower() in {"local", "本机", "@local"} and (
            default_host.protocol.value == "local"
        ):
            # 会话默认已是本机时直接用，避免重复建库
            return default_host, default_cred
        if self.resolve_host is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"步骤 {step.id} 指定了 host={rendered!r}，但未配置主机解析器",
            )
        return self.resolve_host(rendered)

    def _collect_lock_host_ids(
        self,
        playbook: PlaybookSpec,
        default_host: Host,
        default_cred: Credential | None,
        variables: dict[str, Any] | None,
    ) -> list[str]:
        vars_map = self._build_vars(playbook, default_host, variables)
        ids: set[str] = set()
        if default_host.protocol.value != "local":
            ids.add(default_host.id)
        for stage in playbook.stages:
            for step in stage.steps:
                if not step.host:
                    continue
                try:
                    h, _c = self._resolve_step_target(
                        step,
                        default_host=default_host,
                        default_cred=default_cred,
                        variables=vars_map,
                    )
                except AppError:
                    continue
                if h.protocol.value != "local":
                    ids.add(h.id)
        return sorted(ids)

    def _maybe_notify(self, playbook: PlaybookSpec, runtime: SessionRuntime, *, ok: bool) -> None:
        notify_url = None
        if isinstance(playbook.on_failure, dict):
            notify_url = (
                playbook.on_failure.get("notify_on_success_url")
                if ok
                else playbook.on_failure.get("notify_url")
            )
        if not notify_url:
            return
        try:
            import httpx

            httpx.post(
                str(notify_url),
                json={
                    "ok": ok,
                    "playbook": playbook.name,
                    "status": str(runtime.status),
                    "summary": runtime.summary,
                    "session_id": runtime.id,
                },
                timeout=10.0,
            )
        except Exception:  # noqa: BLE001
            logger.exception("notify webhook failed")

    def _check_os(self, host: Host, action_type: str) -> None:
        handler = self.actions.get(action_type)
        os_need = getattr(handler, "os", "any")
        if os_need == "any":
            return
        if host.os_type.value != os_need:
            raise AppError(
                ErrorCode.PROTOCOL_UNSUPPORTED,
                f"动作 {action_type} 需要 {os_need}，当前主机为 {host.os_type.value}",
            )

    @staticmethod
    def _batch_steps(steps: list[StepSpec], *, force_parallel: bool) -> list[list[StepSpec]]:
        if force_parallel and steps:
            return [list(steps)]
        batches: list[list[StepSpec]] = []
        i = 0
        while i < len(steps):
            step = steps[i]
            if step.parallel_group:
                group = step.parallel_group
                batch = [step]
                i += 1
                while i < len(steps) and steps[i].parallel_group == group:
                    batch.append(steps[i])
                    i += 1
                batches.append(batch)
            else:
                batches.append([step])
                i += 1
        return batches

    @staticmethod
    def _apply_host_vars(variables: dict[str, Any], host: Host) -> None:
        variables["host"] = {
            "id": host.id,
            "name": host.name,
            "address": host.address,
            "port": host.port,
            "os_type": host.os_type.value,
            "protocol": host.protocol.value,
        }
        variables["host.address"] = host.address
        variables["host.name"] = host.name
        variables["host.id"] = host.id

    @staticmethod
    def _build_vars(
        playbook: PlaybookSpec,
        host: Host,
        variables: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(playbook.variables)
        if variables:
            merged.update(variables)
        Orchestrator._apply_host_vars(merged, host)
        return merged

    @staticmethod
    def _duration_seconds(
        started: datetime | None, ended: datetime | None
    ) -> float | None:
        if not started or not ended:
            return None
        return max(0.0, (ended - started).total_seconds())

    @staticmethod
    def _format_duration(seconds: float | None) -> str:
        if seconds is None:
            return "—"
        total = int(round(seconds))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}小时{m}分{s}秒"
        if m:
            return f"{m}分{s}秒"
        return f"{s}秒"

    @classmethod
    def _format_session_summary(
        cls,
        runtime: SessionRuntime,
        *,
        playbook_name: str,
        default_host: Host,
    ) -> str:
        started = runtime.started_at
        ended = runtime.ended_at
        # 展示用本地时间
        def _local(dt: datetime | None) -> str:
            if dt is None:
                return "—"
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        ok = sum(1 for s in runtime.steps if s.status == StepStatus.SUCCEEDED)
        failed = sum(1 for s in runtime.steps if s.status == StepStatus.FAILED)
        skipped = sum(1 for s in runtime.steps if s.status == StepStatus.SKIPPED)
        total = len(runtime.steps)
        hosts = sorted(
            {s.host_id for s in runtime.steps if s.host_id}
        )
        duration = cls._duration_seconds(started, ended)
        lines = [
            "════ 执行结果摘要 ════",
            f"流程：{playbook_name}",
            f"状态：{runtime.status}",
            f"默认主机：{default_host.name} ({default_host.protocol.value})",
            f"开始：{_local(started)}",
            f"结束：{_local(ended)}",
            f"耗时：{cls._format_duration(duration)}",
            f"步骤：成功 {ok} / 失败 {failed} / 跳过 {skipped}（共 {total}）",
        ]
        if hosts:
            lines.append(f"涉及主机数：{len(hosts)}")
        if runtime.summary:
            lines.append(f"说明：{runtime.summary}")
        # 列出已执行步骤要点
        if runtime.steps:
            lines.append("执行事项：")
            for s in runtime.steps:
                st = str(s.status).split(".")[-1]
                act = s.action or ""
                step_dur = cls._duration_seconds(s.started_at, s.ended_at)
                lines.append(
                    f"  · [{s.step_key}] {act} → {st}"
                    f"（{cls._format_duration(step_dur)}）"
                )
        lines.append("══════════════════")
        return "\n".join(lines)

    @staticmethod
    def _sleep_cancellable(seconds: float, cancel: threading.Event) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if cancel.is_set():
                raise AppError(ErrorCode.CANCELLED)
            time.sleep(min(0.5, end - time.time()))
