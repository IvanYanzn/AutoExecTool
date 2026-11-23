from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from autoexectool.domain.models import Credential, Host


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class RemoteSession:
    host: Host
    handle: object


class IRemoteConnector(Protocol):
    protocol: str

    def connect(self, host: Host, credential: Credential | None) -> RemoteSession: ...

    def exec(
        self,
        session: RemoteSession,
        command: str,
        timeout: float | None = None,
    ) -> ExecResult: ...

    def upload(self, session: RemoteSession, local: Path, remote: str) -> None: ...

    def download(self, session: RemoteSession, remote: str, local: Path) -> None: ...

    def disconnect(self, session: RemoteSession) -> None: ...
