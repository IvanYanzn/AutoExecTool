from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autoexectool.app.container import AppContainer


class LogCleanupService:
    """按保留天数清理执行日志目录。"""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def cleanup(self, retain_days: int = 30) -> dict[str, int]:
        retain_days = max(1, int(retain_days))
        cutoff = time.time() - retain_days * 86400
        removed_dirs = 0
        removed_files = 0
        root = self.container.paths.logs_exec
        if not root.exists():
            return {"dirs": 0, "files": 0}
        for child in root.iterdir():
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                continue
            if child.is_dir():
                for f in child.rglob("*"):
                    if f.is_file():
                        try:
                            f.unlink()
                            removed_files += 1
                        except OSError:
                            pass
                try:
                    # 自底向上删空目录
                    for d in sorted(child.rglob("*"), reverse=True):
                        if d.is_dir():
                            try:
                                d.rmdir()
                            except OSError:
                                pass
                    child.rmdir()
                    removed_dirs += 1
                except OSError:
                    pass
            elif child.is_file():
                try:
                    child.unlink()
                    removed_files += 1
                except OSError:
                    pass
        # 应用日志：按同策略清理 .log
        app_logs = self.container.paths.logs_app
        if app_logs.exists():
            for f in Path(app_logs).glob("*.log*"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed_files += 1
                except OSError:
                    pass
        return {"dirs": removed_dirs, "files": removed_files}
