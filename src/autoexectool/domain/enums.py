from __future__ import annotations

from enum import StrEnum


class OsType(StrEnum):
    LINUX = "linux"
    WINDOWS = "windows"
    ANY = "any"


class ProtocolType(StrEnum):
    SSH = "ssh"
    WINRM = "winrm"
    LOCAL = "local"


class ExecutionStatus(StrEnum):
    PENDING = "Pending"
    WAITING_UNTIL = "WaitingUntil"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    INTERRUPTED = "Interrupted"
    ROLLED_BACK = "RolledBack"


class StepStatus(StrEnum):
    PENDING = "Pending"
    WAITING_UNTIL = "WaitingUntil"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    CANCELLED = "Cancelled"
