from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.orchestrator.loader import load_playbook_yaml, parse_playbook_dict
from autoexectool.storage.repositories import CredentialRepository, HostRepository

if TYPE_CHECKING:
    from autoexectool.app.container import AppContainer


class SessionService:
    """执行会话查询与重跑。"""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def list_sessions(self, limit: int = 100):
        assert self.container.orchestrator.session_store is not None
        return self.container.orchestrator.session_store.list_sessions(limit=limit)

    def list_steps(self, session_id: str):
        assert self.container.orchestrator.session_store is not None
        return self.container.orchestrator.session_store.list_steps(session_id)

    def rerun(
        self,
        session_id: str,
        *,
        from_failed_step: bool = False,
    ) -> str:
        store = self.container.orchestrator.session_store
        assert store is not None
        row = store.get_session(session_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"会话不存在：{session_id}")

        if row.playbook_json:
            playbook = parse_playbook_dict(json.loads(row.playbook_json))
        elif row.playbook_path and Path(row.playbook_path).exists():
            playbook = load_playbook_yaml(row.playbook_path)
        else:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "该会话缺少 playbook 快照/路径，无法重跑。",
            )

        variables = json.loads(row.variables_json or "{}")
        with self.container.session_factory() as session:
            if not row.host_id:
                raise AppError(ErrorCode.VALIDATION_ERROR, "会话未记录主机，无法重跑。")
            host = HostRepository(session).get(row.host_id)
            cred = None
            if host.credential_id:
                if not self.container.master_keys.is_unlocked:
                    raise AppError(ErrorCode.NOT_INITIALIZED, "重跑远程主机前请解锁主密码。")
                cred = CredentialRepository(session, self.container.vault).get_decrypted(
                    host.credential_id
                )

        start_from = row.failed_step_key if from_failed_step and row.failed_step_key else None
        return self.container.orchestrator.start(
            playbook,
            host,
            credential=cred,
            variables=variables,
            playbook_path=row.playbook_path or "",
            playbook_json=row.playbook_json or "",
            start_from_step=start_from,
            trigger="rerun_failed" if start_from else "rerun_full",
        )
