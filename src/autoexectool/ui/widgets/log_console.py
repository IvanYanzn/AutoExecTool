"""带时间戳与着色的执行输出控制台。"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Literal

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QTextEdit

from autoexectool.orchestrator.timeline import CAT_LABELS, CAT_TO_KIND
from autoexectool.ui.theme import tokens

LogKind = Literal["meta", "info", "stage", "step", "ok", "fail", "warn", "dry"]

_KIND_COLORS: dict[str, str] = {
    "meta": "#6B5B95",
    "info": tokens.TEXT_PRIMARY,
    "stage": tokens.ACCENT,
    "step": "#334155",
    "ok": tokens.SUCCESS,
    "fail": tokens.DANGER,
    "warn": tokens.WARNING,
    "dry": tokens.INFO,
}

_CAT_BADGE: dict[str, str] = {
    "session": tokens.ACCENT,
    "stage": tokens.ACCENT,
    "include": "#7C3AED",
    "node": "#475569",
    "exec": tokens.INFO,
    "return": "#0F766E",
    "output": "#64748B",
    "error": tokens.DANGER,
    "meta": "#6B5B95",
}


class LogConsole(QTextEdit):
    """只读日志区：支持时间线事件（带类别）与普通行。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LogConsole")
        self.setReadOnly(True)
        self.setPlaceholderText("执行输出将显示在这里…")
        self.setAcceptRichText(True)
        font = QFont("Cascadia Mono")
        if not font.exactMatch():
            font = QFont("Consolas")
        if not font.exactMatch():
            font = QFont("Courier New")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)

    def clear_log(self) -> None:
        self.clear()

    def append_line(self, text: str, kind: LogKind | str = "info", *, ts: str | None = None) -> None:
        stamp = ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        color = _KIND_COLORS.get(str(kind), _KIND_COLORS["info"])
        weight = "600" if kind in ("stage", "meta", "fail", "ok") else "400"
        html = (
            f'<span style="color:{tokens.TEXT_SECONDARY};">{escape(stamp)}</span>'
            f"&nbsp;&nbsp;"
            f'<span style="color:{color}; font-weight:{weight};">'
            f"{escape(text)}</span>"
        )
        self.append(html)
        self._scroll_end()

    def append_event(self, event: dict[str, Any]) -> None:
        """按时间线事件的 cat/level 渲染（类别徽章 + 上下文 + 消息）。"""
        ts = str(event.get("ts") or datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        cat = str(event.get("cat") or "meta")
        level = str(event.get("level") or "info")
        label = CAT_LABELS.get(cat, cat)
        badge = _CAT_BADGE.get(cat, tokens.TEXT_SECONDARY)
        kind = CAT_TO_KIND.get(cat, "info")
        if level == "ok":
            kind = "ok"
        elif level == "fail":
            kind = "fail"
        elif level == "warn":
            kind = "warn"
        color = _KIND_COLORS.get(kind, _KIND_COLORS["info"])
        weight = "600" if kind in ("stage", "meta", "fail", "ok") or cat in (
            "session",
            "stage",
            "error",
        ) else "400"

        ctx_bits: list[str] = []
        stage = str(event.get("stage") or "")
        step = str(event.get("step") or "")
        if stage:
            ctx_bits.append(f"阶段={stage}")
        if step:
            ctx_bits.append(f"节点={step}")
        ctx = (" ".join(ctx_bits) + " ") if ctx_bits else ""
        msg = str(event.get("message") or "")

        if "\n" in msg:
            # 多行（步骤输出、结果摘要等）保持换行
            body = (
                escape(ctx)
                + f"<pre style='margin:4px 0 0 0; white-space:pre-wrap;'>{escape(msg)}</pre>"
            )
        else:
            body = escape(ctx + msg)

        html = (
            f'<div style="margin:0 0 3px 0; line-height:1.45;">'
            f'<span style="color:{tokens.TEXT_SECONDARY};">{escape(ts)}</span>'
            f"&nbsp;"
            f'<span style="color:{badge}; font-weight:600;">[{escape(label)}]</span>'
            f"&nbsp;"
            f'<span style="color:{color}; font-weight:{weight};">{body}</span>'
            f"</div>"
        )
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.insertHtml(html + "<br/>")
        self._scroll_end()

    def append_blank(self) -> None:
        self.append("")

    def _scroll_end(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    @staticmethod
    def kind_for_plan_line(line: str) -> LogKind:
        s = line.strip()
        if s.startswith("阶段："):
            return "stage"
        if s.startswith("- [") or (s.startswith("[") and "]" in s):
            return "step"
        return "info"

    @staticmethod
    def kind_for_status(status: object) -> LogKind:
        value = getattr(status, "value", status)
        text = str(value)
        if text in ("Succeeded", "RolledBack"):
            return "ok"
        if text in ("Failed", "Cancelled", "Interrupted"):
            return "fail"
        if text in ("Running", "Pending", "WaitingUntil", "Skipped"):
            return "warn"
        return "info"
