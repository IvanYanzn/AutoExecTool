from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from autoexectool.domain.errors import AppError, ErrorCode


def resolve_execute_at(
    execute_at: str,
    *,
    timezone: str = "Asia/Shanghai",
    now: datetime | None = None,
) -> datetime:
    tz = ZoneInfo(timezone)
    current = now.astimezone(tz) if now else datetime.now(tz)
    text = execute_at.strip()
    # 绝对时间 ISO
    if "T" in text or text.count("-") >= 2:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    # HH:MM 或 HH:MM:SS → 今日，若已过则次日（由 if_past 决定是否立即执行）
    parts = text.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    second = int(parts[2]) if len(parts) > 2 else 0
    candidate = current.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return candidate


def compute_wait_seconds(
    schedule: dict,
    *,
    now: datetime | None = None,
) -> tuple[float, str]:
    """返回 (等待秒数, 说明)。秒数为 0 表示立即执行。"""
    execute_at = schedule.get("execute_at")
    if not execute_at:
        return 0.0, "无计划时间"
    tz_name = schedule.get("timezone") or "Asia/Shanghai"
    if_past = schedule.get("if_past") or "run_immediately"
    max_wait = schedule.get("max_wait_sec")
    target = resolve_execute_at(str(execute_at), timezone=tz_name, now=now)
    tz = ZoneInfo(tz_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    delta = (target - current).total_seconds()
    if delta <= 0:
        if if_past == "fail":
            raise AppError(ErrorCode.SCHEDULE_EXPIRED, detail=f"计划时间 {target.isoformat()}")
        if if_past == "skip":
            return -1.0, "已过点，按策略跳过"
        return 0.0, "已过点，立即执行"
    if max_wait is not None and delta > float(max_wait):
        raise AppError(
            ErrorCode.SCHEDULE_WAIT_TIMEOUT,
            detail=f"需等待 {int(delta)}s，超过 max_wait_sec={max_wait}",
        )
    return delta, f"等待至 {target.isoformat()}"
