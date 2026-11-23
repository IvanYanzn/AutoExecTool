from __future__ import annotations

from typing import Any

from autoexectool.actions.base import IActionHandler
from autoexectool.actions.builtin import (
    CmdExecAction,
    ConditionAction,
    DelayAction,
    FileDownloadAction,
    FileUploadAction,
    FsCopyTreeAction,
    HttpHealthcheckAction,
    NotifyAction,
    PowerShellExecAction,
    ProcessWaitAction,
    ScriptUploadAndRunAction,
    ServiceControlAction,
    ShellExecAction,
    WaitUntilAction,
)
from autoexectool.actions.labels import action_label, format_action
from autoexectool.domain.errors import AppError, ErrorCode


class ActionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, IActionHandler] = {}

    def register(self, handler: IActionHandler) -> None:
        self._items[handler.type] = handler

    def get(self, action_type: str) -> IActionHandler:
        try:
            return self._items[action_type]
        except KeyError as exc:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"未知动作类型：{action_type}",
            ) from exc

    def types(self) -> list[str]:
        return sorted(self._items.keys())

    def canonical_types(self) -> list[str]:
        """去重后的规范动作 code（不含纯别名键）。"""
        return sorted({h.type for h in self._items.values()})

    def display_name(self, action_type: str) -> str:
        handler = self._items.get(action_type)
        custom = getattr(handler, "display_name", None) if handler else None
        if custom:
            return str(custom)
        return action_label(action_type)

    def format(self, action_type: str) -> str:
        return format_action(action_type, self.display_name(action_type))

    def catalog(self, *, include_aliases: bool = False) -> list[dict[str, Any]]:
        """供 UI 展示：name + code + os。"""
        codes = self.types() if include_aliases else self.canonical_types()
        rows: list[dict[str, Any]] = []
        for code in codes:
            handler = self.get(code)
            rows.append(
                {
                    "code": code,
                    "name": self.display_name(code),
                    "os": getattr(handler, "os", "any"),
                    "label": self.format(code),
                }
            )
        return rows


def default_action_registry() -> ActionRegistry:
    registry = ActionRegistry()
    for handler in (
        ShellExecAction(),
        PowerShellExecAction(),
        CmdExecAction(),
        DelayAction(),
        WaitUntilAction(),
        FileUploadAction(),
        FileDownloadAction(),
        ScriptUploadAndRunAction(),
        ProcessWaitAction(),
        ConditionAction(),
        FsCopyTreeAction(),
        HttpHealthcheckAction(),
        NotifyAction(),
        ServiceControlAction(),
    ):
        registry.register(handler)
    # 设计文档简称别名
    aliases = {
        "shell": "shell.exec",
        "powershell": "powershell.exec",
        "cmd": "cmd.exec",
        "delay": "delay",
        "wait.until": "wait.until",
    }
    for alias, target in aliases.items():
        if alias not in registry._items and target in registry._items:
            registry._items[alias] = registry._items[target]
    return registry
