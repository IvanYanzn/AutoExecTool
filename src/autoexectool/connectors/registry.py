from __future__ import annotations

from autoexectool.connectors.base import IRemoteConnector
from autoexectool.connectors.local import LocalConnector
from autoexectool.connectors.ssh import SshConnector
from autoexectool.connectors.winrm_connector import WinRmConnector
from autoexectool.domain.errors import AppError, ErrorCode


class ConnectorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, IRemoteConnector] = {}

    def register(self, connector: IRemoteConnector) -> None:
        self._items[connector.protocol] = connector

    def get(self, protocol: str) -> IRemoteConnector:
        try:
            return self._items[protocol]
        except KeyError as exc:
            raise AppError(
                ErrorCode.PROTOCOL_UNSUPPORTED,
                f"未注册的连接协议：{protocol}",
            ) from exc

    def protocols(self) -> list[str]:
        return sorted(self._items.keys())


def default_connector_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(LocalConnector())
    registry.register(SshConnector())
    registry.register(WinRmConnector())
    return registry
