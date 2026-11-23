from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from autoexectool.connectors.base import IRemoteConnector, RemoteSession
from autoexectool.domain.models import ActionResult, Host


@dataclass
class ExecutionContext:
    host: Host
    connector: IRemoteConnector
    session: RemoteSession
    variables: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    cancel: threading.Event | None = None


class IActionHandler(Protocol):
    type: str
    os: str  # linux | windows | any

    def validate(self, params: dict[str, Any]) -> None: ...

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult: ...
