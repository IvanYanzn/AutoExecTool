"""任务开始/结束等生命周期提示（非模态，不挡住日志刷新）。"""

from __future__ import annotations

from weakref import WeakKeyDictionary

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QWidget

# 防止非模态框被 GC
_open_boxes: WeakKeyDictionary[QWidget, list[QMessageBox]] = WeakKeyDictionary()


def popup(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    error: bool = False,
    auto_close_ms: int = 5000,
) -> None:
    """弹出提示；默认非模态，几秒后自动关闭（仍可手动点 OK）。"""
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(text)
    mb.setIcon(
        QMessageBox.Icon.Critical if error else QMessageBox.Icon.Information
    )
    mb.setStandardButtons(QMessageBox.StandardButton.Ok)
    # 非模态：不阻塞主窗口，也不影响其他执行标签继续点「执行」
    mb.setModal(False)
    mb.show()
    mb.raise_()

    if parent is not None:
        boxes = _open_boxes.setdefault(parent, [])
        boxes.append(mb)

        def _cleanup(result: int = 0) -> None:  # noqa: ARG001
            lst = _open_boxes.get(parent)
            if lst and mb in lst:
                lst.remove(mb)

        mb.finished.connect(_cleanup)

    if auto_close_ms > 0:
        QTimer.singleShot(auto_close_ms, mb.close)
