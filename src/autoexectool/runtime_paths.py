from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """用户可写的安装根：exe 所在目录（开发时为项目 AutoExecTool/）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # src/autoexectool/runtime_paths.py → parents[2] = AutoExecTool/
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    """只读资源根：打包后为 _MEIPASS（含 templates/plugins）；开发时同 install_root。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return install_root() / "_internal"
    return install_root()


def templates_dir() -> Path:
    """内置只读示例/产品模板（打包在 _internal/templates）。"""
    return bundle_root() / "templates"


def playbooks_dir() -> Path:
    """业务/现场可写编排（data/config/playbooks），与 templates 分离。"""
    from autoexectool.storage.paths import resolve_data_paths

    return resolve_data_paths().playbooks


def plugins_dir() -> Path:
    return bundle_root() / "plugins"
