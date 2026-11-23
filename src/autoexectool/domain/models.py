from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType, StepStatus


@dataclass
class Host:
    id: str
    name: str
    address: str
    port: int
    os_type: OsType
    protocol: ProtocolType
    credential_id: str | None = None
    tags: list[str] = field(default_factory=list)
    remark: str = ""


@dataclass
class HostGroup:
    id: str
    name: str
    remark: str = ""
    host_ids: list[str] = field(default_factory=list)


@dataclass
class Credential:
    id: str
    name: str
    auth_type: str
    # 解密后的明文仅存在内存短时使用，不落盘
    username: str = ""
    password: str = ""
    private_key_pem: str = ""
    private_key_passphrase: str = ""


@dataclass
class ActionResult:
    success: bool
    exit_code: int | None = None
    message: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class StepSpec:
    id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    schedule: dict[str, Any] | None = None
    timeout_sec: int | None = None
    retries: int = 0
    retry_interval_sec: int = 3
    use_group: str | None = None
    success_when: dict[str, Any] | None = None
    parallel_group: str | None = None
    # 步骤级目标：主机 id / 名称 / local|本机；空则用会话默认主机
    host: str | None = None
    # 引用子流程（YAML 路径或相对 templates/父流程目录）；展开后替换为本步
    use_playbook: str | None = None
    # 引用子流程时的变量覆盖（优先级最高）
    playbook_vars: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageSpec:
    name: str
    steps: list[StepSpec] = field(default_factory=list)
    parallel: bool = False


@dataclass
class PlaybookSpec:
    name: str
    version: int = 1
    variables: dict[str, Any] = field(default_factory=dict)
    stages: list[StageSpec] = field(default_factory=list)
    on_failure: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class StepRuntime:
    step_key: str
    status: StepStatus = StepStatus.PENDING
    host_id: str | None = None
    action: str = ""
    exit_code: int | None = None
    log_path: str | None = None
    message: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None


@dataclass
class SessionRuntime:
    id: str
    playbook_name: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    steps: list[StepRuntime] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: str = ""
