from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from croniter import croniter
from sqlalchemy import select

from autoexectool.domain.enums import OsType, ProtocolType
from autoexectool.domain.models import Host
from autoexectool.logging.setup import get_logger
from autoexectool.orchestrator.loader import load_playbook_yaml
from autoexectool.storage.models import ScheduleRow
from autoexectool.storage.repositories import CredentialRepository, HostRepository

if TYPE_CHECKING:
    from autoexectool.app.container import AppContainer

logger = get_logger("scheduler")

# 同一扫描批次内并行跑调度任务的上限
_MAX_PARALLEL_FIRES = 8


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _as_local(dt: datetime) -> datetime:
    """转为本地时区。数据库中的 naive datetime 按 UTC 解释（SQLAlchemy 惯例）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _to_utc_for_db(dt: datetime) -> datetime:
    """UI/本地时刻 → 存库用的 UTC（带 tzinfo，写入时由方言规范）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_local_now().tzinfo)
    return dt.astimezone(timezone.utc)


class SchedulerService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_fire: dict[str, datetime] = {}
        self._fire_lock = threading.Lock()

    def list_schedules(self) -> list[ScheduleRow]:
        with self.container.session_factory() as session:
            return list(
                session.scalars(select(ScheduleRow).order_by(ScheduleRow.name)).all()
            )

    def upsert(
        self,
        *,
        name: str,
        playbook_path: str,
        mode: str = "cron",
        cron: str = "",
        run_at: datetime | None = None,
        host_id: str | None = None,
        enabled: bool = True,
        schedule_id: str | None = None,
    ) -> str:
        mode = (mode or "cron").strip().lower()
        if mode not in {"cron", "once"}:
            raise ValueError("mode 须为 cron 或 once")
        if mode == "cron":
            if not cron.strip():
                raise ValueError("周期调度须填写 Cron")
            croniter(cron.strip(), _local_now())
            run_at = None
        else:
            if run_at is None:
                raise ValueError("一次性调度须指定执行时间")
            # 统一存 UTC，避免 SQLite 丢时区后被误当成 UTC 再 +8 小时
            run_at = _to_utc_for_db(run_at)
            cron = ""

        with self.container.session_factory() as session:
            row = session.get(ScheduleRow, schedule_id) if schedule_id else None
            if row is None:
                row = ScheduleRow(id=schedule_id or str(uuid.uuid4()))
                session.add(row)
            row.name = name
            row.mode = mode
            row.cron = cron.strip()
            row.run_at = run_at
            row.playbook_path = playbook_path
            row.host_id = host_id
            row.enabled = 1 if enabled else 0
            # 重新保存的一次性任务视为尚未执行
            if mode == "once":
                row.last_run_at = None
                row.last_status = ""
            session.commit()
            return row.id

    def delete(self, schedule_id: str) -> None:
        with self.container.session_factory() as session:
            row = session.get(ScheduleRow, schedule_id)
            if row:
                session.delete(row)
                session.commit()

    def set_enabled(self, schedule_id: str, enabled: bool) -> None:
        with self.container.session_factory() as session:
            row = session.get(ScheduleRow, schedule_id)
            if row:
                row.enabled = 1 if enabled else 0
                session.commit()

    def start_background(self, interval_sec: float = 20.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(interval_sec,), name="aet-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick_once(self, now: datetime | None = None) -> list[str]:
        """扫描到期任务并**并行**触发；返回触发的 schedule id 列表。

        - cron：按本机本地时区解释（如 ``30 17 * * *`` = 每天 17:30）
        - once：到 ``run_at`` 执行一次后自动停用
        - 执行走与手动相同的编排会话：执行记录 + timeline.jsonl 完整日志
        """
        now = now.astimezone() if now and now.tzinfo else _as_local(now or _local_now())
        due: list[tuple[ScheduleRow, bool]] = []

        for row in self.list_schedules():
            if not row.enabled:
                continue
            try:
                mode = (getattr(row, "mode", None) or "cron").lower()
                if mode == "once":
                    if self._should_fire_once(row, now):
                        due.append((row, True))
                    continue

                if not row.cron:
                    continue
                itr = croniter(row.cron, now)
                prev_time = itr.get_prev(datetime)
                if prev_time.tzinfo is None:
                    prev_time = prev_time.replace(tzinfo=now.tzinfo)
                prev_time = prev_time.astimezone(now.tzinfo)
                with self._fire_lock:
                    last = self._last_fire.get(row.id)
                if last is not None:
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if last.astimezone(now.tzinfo) >= prev_time:
                        continue
                if (now - prev_time).total_seconds() > 120:
                    with self._fire_lock:
                        self._last_fire[row.id] = prev_time
                    continue
                due.append((row, False))
            except Exception as exc:  # noqa: BLE001
                logger.exception("schedule %s due-check failed: %s", row.id, exc)
                self._mark_failed(row.id, exc)

        if not due:
            return []

        # 先记账，避免本批次执行期间被重复点名
        with self._fire_lock:
            for row, _disable in due:
                self._last_fire[row.id] = now

        fired: list[str] = []
        workers = min(_MAX_PARALLEL_FIRES, len(due))
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="aet-sched"
        ) as pool:
            futures = {
                pool.submit(self._run_schedule, row, disable_after=disable): row.id
                for row, disable in due
            }
            for fut in as_completed(futures):
                sid = futures[fut]
                try:
                    fut.result()
                    fired.append(sid)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("schedule %s failed: %s", sid, exc)
                    self._mark_failed(sid, exc)
        return fired

    def _should_fire_once(self, row: ScheduleRow, now: datetime) -> bool:
        if row.run_at is None:
            return False
        if row.last_run_at is not None:
            return False
        run_at = _as_local(row.run_at)
        return now >= run_at

    def _loop(self, interval_sec: float) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler tick error")
            self._stop.wait(interval_sec)

    def _mark_failed(self, schedule_id: str, exc: BaseException) -> None:
        with self.container.session_factory() as session:
            db_row = session.get(ScheduleRow, schedule_id)
            if db_row:
                db_row.last_status = f"Failed: {exc}"
                session.commit()

    def _run_schedule(self, row: ScheduleRow, *, disable_after: bool) -> str:
        """触发一次流程执行：写入执行会话与 timeline，与手动执行同一套链路。"""
        playbook = load_playbook_yaml(Path(row.playbook_path))
        with self.container.session_factory() as session:
            if row.host_id:
                host = HostRepository(session).get(row.host_id)
                cred = None
                if host.credential_id and self.container.master_keys.is_unlocked:
                    cred = CredentialRepository(
                        session, self.container.vault
                    ).get_decrypted(host.credential_id)
            else:
                # 每条调度用独立 local id，避免无意义的串扰；local 本身不占主机锁
                host = Host(
                    id=f"sched-local-{row.id}",
                    name="local",
                    address="127.0.0.1",
                    port=0,
                    os_type=OsType.WINDOWS if __import__("os").name == "nt" else OsType.LINUX,
                    protocol=ProtocolType.LOCAL,
                )
                cred = None
            host_copy = host
            cred_copy = cred

        session_id = self.container.orchestrator.start(
            playbook,
            host_copy,
            credential=cred_copy,
            dry_run=False,
            playbook_path=row.playbook_path,
            trigger="schedule",
        )
        runtime = self.container.orchestrator.get_status(session_id)
        with self.container.session_factory() as session:
            db_row = session.get(ScheduleRow, row.id)
            if db_row:
                db_row.last_run_at = datetime.now(timezone.utc)
                status_text = str(runtime.status)
                if disable_after:
                    db_row.enabled = 0
                    if not status_text.startswith("Failed"):
                        status_text = f"{status_text}（仅一次，已停用）"
                db_row.last_status = f"{status_text} · session={session_id[:8]}"
                session.commit()
        logger.info(
            "schedule %s -> session %s (%s) [parallel-capable]",
            row.id,
            session_id,
            runtime.status,
        )
        return session_id
