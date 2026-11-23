from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from typing import TYPE_CHECKING

from autoexectool.domain.errors import AppError, ErrorCode

if TYPE_CHECKING:
    from autoexectool.app.container import AppContainer


class BackupService:
    """备份/恢复 data 目录（完整版必达）。"""

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def create_backup(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        out_dir = self.container.paths.backups / "data_snapshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        archive = out_dir / f"data_{ts}"
        # 排除临时与过大日志可选；此处备份整个 data root（不含自身 backups 嵌套爆炸时仍可接受）
        root = self.container.paths.root
        # 使用 zip
        zip_path = shutil.make_archive(str(archive), "zip", root_dir=root)
        return Path(zip_path)

    def restore_backup(self, zip_path: Path) -> None:
        if not zip_path.exists():
            raise AppError(ErrorCode.VALIDATION_ERROR, f"备份文件不存在：{zip_path}")
        target = self.container.paths.root
        tmp = self.container.paths.tmp / "restore_unpack"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(str(zip_path), extract_dir=tmp)
        # 覆盖关键子目录
        for name in ("config", "db"):
            src = tmp / name
            dest = target / name
            if not src.exists():
                continue
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
