from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from autoexectool.domain.enums import ExecutionStatus
from autoexectool.domain.models import SessionRuntime, StepRuntime
from autoexectool.storage.models import ExecutionSessionRow, ExecutionStepRow


class SessionStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def mark_interrupted_running(self) -> int:
        """启动时将未结束会话标记为 Interrupted。"""
        with self.session_factory() as session:
            rows = session.scalars(
                select(ExecutionSessionRow).where(
                    ExecutionSessionRow.status.in_(
                        [
                            ExecutionStatus.PENDING.value,
                            ExecutionStatus.RUNNING.value,
                            ExecutionStatus.WAITING_UNTIL.value,
                        ]
                    )
                )
            ).all()
            count = 0
            for row in rows:
                row.status = ExecutionStatus.INTERRUPTED.value
                row.summary = (row.summary or "") + " | 进程重启标记为 Interrupted"
                row.ended_at = datetime.now(timezone.utc)
                count += 1
            session.commit()
            return count

    def create_session(
        self,
        *,
        session_id: str,
        playbook_name: str,
        playbook_path: str = "",
        playbook_json: str = "",
        host_id: str | None = None,
        variables: dict[str, Any] | None = None,
        trigger: str = "manual",
        operator: str = "",
    ) -> None:
        with self.session_factory() as session:
            session.add(
                ExecutionSessionRow(
                    id=session_id,
                    playbook_name=playbook_name,
                    playbook_path=playbook_path,
                    playbook_json=playbook_json,
                    host_id=host_id,
                    variables_json=json.dumps(variables or {}, ensure_ascii=False),
                    trigger=trigger,
                    status=ExecutionStatus.RUNNING.value,
                    started_at=datetime.now(timezone.utc),
                    operator=operator,
                    summary="执行中",
                )
            )
            session.commit()

    def sync_runtime(self, runtime: SessionRuntime) -> None:
        with self.session_factory() as session:
            row = session.get(ExecutionSessionRow, runtime.id)
            if row is None:
                return
            row.status = str(runtime.status)
            row.summary = runtime.summary or ""
            row.ended_at = runtime.ended_at
            failed = next(
                (s for s in runtime.steps if str(s.status) == "Failed"),
                None,
            )
            row.failed_step_key = failed.step_key if failed else ""
            # 重建步骤行（简单可靠）
            old_steps = session.scalars(
                select(ExecutionStepRow).where(ExecutionStepRow.session_id == runtime.id)
            ).all()
            for s in old_steps:
                session.delete(s)
            for step in runtime.steps:
                session.add(
                    ExecutionStepRow(
                        id=str(uuid.uuid4()),
                        session_id=runtime.id,
                        step_key=step.step_key,
                        host_id=step.host_id,
                        action=step.action,
                        status=str(step.status),
                        exit_code=step.exit_code,
                        log_path=step.log_path,
                        message=step.message or "",
                        started_at=step.started_at,
                        ended_at=step.ended_at,
                    )
                )
            session.commit()

    def list_sessions(self, limit: int = 100) -> Sequence[ExecutionSessionRow]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ExecutionSessionRow)
                    .order_by(ExecutionSessionRow.started_at.desc())
                    .limit(limit)
                ).all()
            )

    def get_session(self, session_id: str) -> ExecutionSessionRow | None:
        with self.session_factory() as session:
            return session.get(ExecutionSessionRow, session_id)

    def list_steps(self, session_id: str) -> Sequence[ExecutionStepRow]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ExecutionStepRow)
                    .where(ExecutionStepRow.session_id == session_id)
                    .order_by(ExecutionStepRow.started_at.asc())
                ).all()
            )
