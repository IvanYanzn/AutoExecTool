from __future__ import annotations

import json
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.storage.models import (
    ApplicationRow,
    EnvironmentRow,
    ReleasePackageRow,
    ReleaseRecordRow,
)


class PublishRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- applications ---
    def list_apps(self) -> Sequence[ApplicationRow]:
        return self.session.scalars(select(ApplicationRow).order_by(ApplicationRow.name)).all()

    def get_app(self, app_id: str) -> ApplicationRow:
        row = self.session.get(ApplicationRow, app_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"应用不存在：{app_id}")
        return row

    def get_app_by_name(self, name: str) -> ApplicationRow | None:
        return self.session.scalars(
            select(ApplicationRow).where(ApplicationRow.name == name)
        ).first()

    def save_app(
        self,
        *,
        name: str,
        app_type: str = "dir",
        default_port: int = 0,
        description: str = "",
        deploy_dir: str = "",
        app_id: str | None = None,
    ) -> ApplicationRow:
        row = self.session.get(ApplicationRow, app_id) if app_id else None
        if row is None:
            existing = self.get_app_by_name(name)
            if existing and not app_id:
                row = existing
            else:
                row = ApplicationRow(id=app_id or str(uuid.uuid4()))
                self.session.add(row)
        row.name = name
        row.app_type = app_type
        row.default_port = default_port
        row.description = description
        row.deploy_dir = deploy_dir
        self.session.commit()
        return row

    # --- environments ---
    def list_envs(self, app_id: str | None = None) -> Sequence[EnvironmentRow]:
        stmt = select(EnvironmentRow).order_by(EnvironmentRow.name)
        if app_id:
            stmt = stmt.where(EnvironmentRow.app_id == app_id)
        return self.session.scalars(stmt).all()

    def get_env(self, env_id: str) -> EnvironmentRow:
        row = self.session.get(EnvironmentRow, env_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"环境不存在：{env_id}")
        return row

    def save_env(
        self,
        *,
        name: str,
        app_id: str,
        host_id: str | None = None,
        variables: dict | None = None,
        env_id: str | None = None,
    ) -> EnvironmentRow:
        row = self.session.get(EnvironmentRow, env_id) if env_id else None
        if row is None:
            row = EnvironmentRow(id=env_id or str(uuid.uuid4()))
            self.session.add(row)
        row.name = name
        row.app_id = app_id
        row.host_id = host_id
        row.vars_json = json.dumps(variables or {}, ensure_ascii=False)
        self.session.commit()
        return row

    # --- packages ---
    def list_packages(self, app_id: str) -> Sequence[ReleasePackageRow]:
        return self.session.scalars(
            select(ReleasePackageRow)
            .where(ReleasePackageRow.app_id == app_id)
            .order_by(ReleasePackageRow.created_at.desc())
        ).all()

    def get_package(self, package_id: str) -> ReleasePackageRow:
        row = self.session.get(ReleasePackageRow, package_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"制品不存在：{package_id}")
        return row

    def save_package(
        self,
        *,
        app_id: str,
        version: str,
        path: str,
        checksum: str = "",
        note: str = "",
    ) -> ReleasePackageRow:
        row = ReleasePackageRow(
            id=str(uuid.uuid4()),
            app_id=app_id,
            version=version,
            path=path,
            checksum=checksum,
            note=note,
        )
        self.session.add(row)
        self.session.commit()
        return row

    # --- records ---
    def list_records(self, app_id: str | None = None, limit: int = 50) -> Sequence[ReleaseRecordRow]:
        stmt = select(ReleaseRecordRow).order_by(ReleaseRecordRow.created_at.desc()).limit(limit)
        if app_id:
            stmt = stmt.where(ReleaseRecordRow.app_id == app_id)
        return self.session.scalars(stmt).all()

    def get_record(self, record_id: str) -> ReleaseRecordRow:
        row = self.session.get(ReleaseRecordRow, record_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"发布记录不存在：{record_id}")
        return row

    def latest_success(self, app_id: str, env_id: str) -> ReleaseRecordRow | None:
        return self.session.scalars(
            select(ReleaseRecordRow)
            .where(
                ReleaseRecordRow.app_id == app_id,
                ReleaseRecordRow.env_id == env_id,
                ReleaseRecordRow.status == "Succeeded",
            )
            .order_by(ReleaseRecordRow.created_at.desc())
        ).first()

    def add_record(self, **kwargs) -> ReleaseRecordRow:
        row = ReleaseRecordRow(id=kwargs.pop("id", str(uuid.uuid4())), **kwargs)
        self.session.add(row)
        self.session.commit()
        return row

    def update_record(self, record_id: str, **kwargs) -> ReleaseRecordRow:
        row = self.get_record(record_id)
        for k, v in kwargs.items():
            setattr(row, k, v)
        self.session.commit()
        return row
