"""执行会话时间线（JSONL）：引擎只写、界面只读。

每行一个事件，含 ``cat`` 类别，便于 UI 按类型渲染与筛选。

类别约定：
- session  会话开始/结束
- stage    阶段（流程分段）
- include  流程引用展开（use_playbook）
- node     节点（步骤）状态（可含 duration_sec）
- exec     实际执行内容（命令/上传路径等）
- return   返回摘要（exit_code、success、message）
- output   标准输出/错误预览（全文在同目录 .out/.err）
- error    错误与异常
- meta     其它说明
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from autoexectool.orchestrator.masking import mask_secrets

# 界面展示用类别标签
CAT_LABELS: dict[str, str] = {
    "session": "会话",
    "stage": "阶段",
    "include": "引用",
    "node": "节点",
    "exec": "执行",
    "return": "返回",
    "output": "输出",
    "error": "错误",
    "meta": "信息",
}

# 类别 → 日志着色 kind
CAT_TO_KIND: dict[str, str] = {
    "session": "meta",
    "stage": "stage",
    "include": "meta",
    "node": "step",
    "exec": "info",
    "return": "info",
    "output": "info",
    "error": "fail",
    "meta": "meta",
}


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def preview_text(text: str, *, max_chars: int = 4000, max_lines: int = 80) -> str:
    """截断大段输出，避免时间线膨胀；全文仍写独立文件。"""
    text = mask_secrets(text or "")
    if not text:
        return ""
    lines = text.splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars]
        truncated = True
    if truncated:
        body += "\n…（已截断，完整内容见同目录步骤日志文件）"
    return body


def summarize_exec(action: str, params: dict[str, Any]) -> str:
    """从动作参数提炼「执行了什么」。"""
    if "command" in params and params["command"] is not None:
        return mask_secrets(str(params["command"]))
    parts: list[str] = [action]
    for key in ("local", "remote", "path", "src", "dest", "url", "script"):
        if key in params and params[key] is not None:
            parts.append(f"{key}={params[key]}")
    if len(parts) == 1:
        safe = {k: v for k, v in params.items() if not str(k).lower().endswith("password")}
        return mask_secrets(f"{action} {safe}")
    return mask_secrets(" ".join(parts))


class TimelineWriter:
    """追加写入 ``timeline.jsonl``（线程安全）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def emit(
        self,
        cat: str,
        message: str,
        *,
        level: str = "info",
        stage: str = "",
        step: str = "",
        action: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "ts": _now_ts(),
            "cat": cat,
            "level": level,
            "stage": stage,
            "step": step,
            "action": action,
            "message": mask_secrets(message),
        }
        if data:
            event["data"] = data
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()


class TimelineReader:
    """按字节偏移增量读取时间线（供 UI Tail）。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._offset = 0

    def reset(self) -> None:
        self._offset = 0

    def read_new(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            fh.seek(self._offset)
            chunk = fh.read()
            self._offset = fh.tell()
        for raw in chunk.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                events.append(
                    {
                        "ts": _now_ts(),
                        "cat": "error",
                        "level": "fail",
                        "message": f"时间线解析失败：{raw[:120]}",
                    }
                )
        return events

    def iter_all(self) -> Iterator[dict[str, Any]]:
        self.reset()
        while True:
            batch = self.read_new()
            if not batch:
                break
            yield from batch


def format_event_line(event: dict[str, Any]) -> tuple[str, str, str]:
    """返回 (timestamp, kind, display_text) 供控制台渲染。"""
    ts = str(event.get("ts") or _now_ts())
    cat = str(event.get("cat") or "meta")
    level = str(event.get("level") or "info")
    label = CAT_LABELS.get(cat, cat)
    msg = str(event.get("message") or "")
    step = str(event.get("step") or "")
    stage = str(event.get("stage") or "")
    prefix_bits = [f"[{label}]"]
    if stage:
        prefix_bits.append(f"阶段={stage}")
    if step:
        prefix_bits.append(f"节点={step}")
    text = " ".join(prefix_bits) + (f" {msg}" if msg else "")

    kind = CAT_TO_KIND.get(cat, "info")
    if level == "ok":
        kind = "ok"
    elif level == "fail":
        kind = "fail"
    elif level == "warn":
        kind = "warn"
    return ts, kind, text
