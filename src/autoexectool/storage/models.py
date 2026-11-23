from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class HostRow(Base):
    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    os_type: Mapped[str] = mapped_column(String(32), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HostGroupRow(Base):
    __tablename__ = "host_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HostGroupMemberRow(Base):
    __tablename__ = "host_group_members"

    group_id: Mapped[str] = mapped_column(ForeignKey("host_groups.id"), primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"), primary_key=True)


class CredentialRow(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlaybookRow(Base):
    __tablename__ = "playbooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    yaml_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExecutionSessionRow(Base):
    __tablename__ = "execution_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    playbook_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    playbook_name: Mapped[str] = mapped_column(String(128), default="")
    playbook_path: Mapped[str] = mapped_column(String(1024), default="")
    playbook_json: Mapped[str] = mapped_column(Text, default="")
    host_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    variables_json: Mapped[str] = mapped_column(Text, default="{}")
    trigger: Mapped[str] = mapped_column(String(64), default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    failed_step_key: Mapped[str] = mapped_column(String(128), default="")


class ExecutionStepRow(Base):
    __tablename__ = "execution_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("execution_sessions.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    host_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class CommandGroupRow(Base):
    __tablename__ = "command_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VariableSetRow(Base):
    __tablename__ = "variable_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    vars_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ApplicationRow(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    app_type: Mapped[str] = mapped_column(String(64), default="dir")
    default_port: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    deploy_dir: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EnvironmentRow(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    app_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), nullable=False)
    host_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vars_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReleasePackageRow(Base):
    __tablename__ = "release_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReleaseRecordRow(Base):
    __tablename__ = "release_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), nullable=False)
    env_id: Mapped[str] = mapped_column(ForeignKey("environments.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    backup_ref: Mapped[str] = mapped_column(String(1024), default="")
    operator: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScheduleRow(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # cron=周期；once=指定时刻仅执行一次（触发后自动停用）
    mode: Mapped[str] = mapped_column(String(16), default="cron")
    cron: Mapped[str] = mapped_column(String(128), default="")
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    playbook_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    host_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

