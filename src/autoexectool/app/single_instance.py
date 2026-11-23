from __future__ import annotations

import atexit
import os
from pathlib import Path

from autoexectool.domain.errors import AppError, ErrorCode


class SingleInstanceLock:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self._fd: int | None = None

    def acquire(self) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_file.exists():
            # 简单策略：存在则认为已运行（完整版可加强 PID 探活）
            try:
                old_pid = int(self.lock_file.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                old_pid = 0
            if old_pid and _pid_alive(old_pid):
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "AutoExecTool 已在运行（单实例）。",
                    detail=f"pid={old_pid}",
                )
        self.lock_file.write_text(str(os.getpid()), encoding="utf-8")
        self._fd = 1
        atexit.register(self.release)

    def release(self) -> None:
        try:
            if self.lock_file.exists():
                self.lock_file.unlink(missing_ok=True)
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except AttributeError:
        # Windows 上 os.kill 可用；若异常则保守认为存活
        return True
    else:
        return True
