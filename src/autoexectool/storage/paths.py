from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    root: Path
    config: Path
    keys: Path
    playbooks: Path
    db_dir: Path
    db_file: Path
    logs_app: Path
    logs_exec: Path
    packages: Path
    scripts: Path
    backups: Path
    tmp: Path

    def ensure(self) -> None:
        for p in (
            self.config,
            self.keys,
            self.playbooks,
            self.db_dir,
            self.logs_app,
            self.logs_exec,
            self.packages,
            self.scripts,
            self.backups,
            self.tmp,
        ):
            p.mkdir(parents=True, exist_ok=True)


def _default_root() -> Path:
    env = os.environ.get("AUTOEXECTOOL_DATA")
    if env:
        return Path(env).expanduser().resolve()
    # 开发：项目旁 data/；绿色包：exe 旁 data/（可写）
    from autoexectool.runtime_paths import install_root

    return (install_root() / "data").resolve()


def resolve_data_paths(root: Path | None = None) -> DataPaths:
    base = (root or _default_root()).resolve()
    paths = DataPaths(
        root=base,
        config=base / "config",
        keys=base / "config" / "keys",
        playbooks=base / "config" / "playbooks",
        db_dir=base / "db",
        db_file=base / "db" / "AutoExecTool.db",
        logs_app=base / "logs" / "app",
        logs_exec=base / "logs" / "executions",
        packages=base / "packages",
        scripts=base / "scripts",
        backups=base / "backups",
        tmp=base / "tmp",
    )
    paths.ensure()
    return paths
