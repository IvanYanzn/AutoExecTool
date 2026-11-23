from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PySide6.QtWidgets import QApplication


def _load_qss() -> str:
    # 1) 包内资源（开发 editable 安装 / 正确打进包数据时）
    try:
        text = files("autoexectool.ui.theme").joinpath("app.qss").read_text(encoding="utf-8")
        if text.strip():
            return text
    except Exception:  # noqa: BLE001
        pass
    # 2) 与本文件同目录（源码树直接运行）
    beside = Path(__file__).with_name("app.qss")
    if beside.exists():
        return beside.read_text(encoding="utf-8")
    # 3) PyInstaller：_MEIPASS/autoexectool/ui/theme/app.qss
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "autoexectool" / "ui" / "theme" / "app.qss"
        if bundled.exists():
            return bundled.read_text(encoding="utf-8")
    return ""


def apply_theme(app: QApplication) -> None:
    qss = _load_qss()
    if qss:
        app.setStyleSheet(qss)
