from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _step_kind(step: dict[str, Any]) -> str:
    if step.get("use_playbook"):
        return "playbook"
    if step.get("use_group"):
        return "group"
    return "action"


def _step_title(step: dict[str, Any]) -> str:
    kind = _step_kind(step)
    if kind == "playbook":
        return f"引用流程 · {step.get('use_playbook')}"
    if kind == "group":
        return f"指令组 · {step.get('use_group')}"
    return str(step.get("action") or "?")


def _step_meta_line(step: dict[str, Any]) -> str:
    parts: list[str] = []
    host = step.get("host")
    if host:
        parts.append(f"@{host}")
    pg = step.get("parallel_group")
    if pg:
        parts.append(f"‖{pg}")
    sched = step.get("schedule") or {}
    if isinstance(sched, dict) and sched.get("execute_at"):
        parts.append(f"⏰ {sched.get('execute_at')}")
    sw = step.get("success_when") or {}
    if isinstance(sw, dict) and "exit_code" in sw:
        parts.append(f"exit={sw.get('exit_code')}")
    return " · ".join(parts)


class FlowStepCard(QFrame):
    clicked = Signal(int, int)

    def __init__(
        self,
        stage_idx: int,
        step_idx: int,
        step: dict[str, Any],
        *,
        selected: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.stage_idx = stage_idx
        self.step_idx = step_idx
        self.setObjectName("FlowStepCardSelected" if selected else "FlowStepCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        sid = str(step.get("id") or f"step{step_idx + 1}")
        head = QLabel(f"{step_idx + 1}. [{sid}]")
        head.setObjectName("FlowStepId")
        layout.addWidget(head)

        title = QLabel(_step_title(step))
        title.setObjectName("FlowStepTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = _step_meta_line(step)
        if meta:
            meta_lbl = QLabel(meta)
            meta_lbl.setObjectName("FlowStepMeta")
            meta_lbl.setWordWrap(True)
            layout.addWidget(meta_lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.stage_idx, self.step_idx)
        super().mousePressEvent(event)


class FlowCanvas(QScrollArea):
    """实时渲染 stages → steps 的可视化画布。"""

    selection_changed = Signal(int, int)  # stage_idx, step_idx；清空为 -1,-1
    add_step_requested = Signal(int)  # stage_idx
    add_stage_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._host = QWidget()
        self._host.setObjectName("FlowCanvasHost")
        self._root = QHBoxLayout(self._host)
        self._root.setContentsMargins(8, 8, 8, 8)
        self._root.setSpacing(16)
        self._root.addStretch(1)
        self.setWidget(self._host)

        self._selected: tuple[int, int] | None = None
        self._data: dict[str, Any] = {}

    @property
    def selected(self) -> tuple[int, int] | None:
        return self._selected

    def clear_selection(self) -> None:
        self._selected = None
        self.selection_changed.emit(-1, -1)
        self.render(self._data)

    def select(self, stage_idx: int, step_idx: int) -> None:
        self._selected = (stage_idx, step_idx)
        self.selection_changed.emit(stage_idx, step_idx)
        self.render(self._data)

    def render(self, data: dict[str, Any]) -> None:
        self._data = data if isinstance(data, dict) else {}
        while self._root.count():
            item = self._root.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        stages = self._data.get("stages") or []
        if not stages:
            empty = QLabel("暂无阶段。点「添加阶段」或在 YAML 中编写 stages。")
            empty.setObjectName("MutedLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._root.addWidget(empty, 1)
            return

        for si, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            self._root.addWidget(self._build_stage(si, stage), 0)
            if si < len(stages) - 1:
                arrow = QLabel("→")
                arrow.setObjectName("FlowStageArrow")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._root.addWidget(arrow, 0)

        add_stage = QPushButton("+ 阶段")
        add_stage.setObjectName("FlowGhostButton")
        add_stage.setToolTip("在末尾添加一个新阶段")
        add_stage.clicked.connect(self.add_stage_requested.emit)
        self._root.addWidget(add_stage, 0)
        self._root.addStretch(1)

    def _build_stage(self, stage_idx: int, stage: dict[str, Any]) -> QWidget:
        frame = QFrame()
        frame.setObjectName("FlowStageFrame")
        frame.setMinimumWidth(240)
        frame.setMaximumWidth(320)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        name = str(stage.get("name") or f"stage{stage_idx + 1}")
        header = QLabel(f"阶段 {stage_idx + 1} · {name}")
        header.setObjectName("FlowStageHeader")
        header.setWordWrap(True)
        layout.addWidget(header)

        if stage.get("parallel"):
            badge = QLabel("阶段内并行")
            badge.setObjectName("FlowBadge")
            layout.addWidget(badge)

        steps = stage.get("steps") or []
        if not steps:
            empty = QLabel("（空阶段）")
            empty.setObjectName("MutedLabel")
            layout.addWidget(empty)
        else:
            for ti, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                selected = self._selected == (stage_idx, ti)
                card = FlowStepCard(stage_idx, ti, step, selected=selected)
                card.clicked.connect(self._on_card_clicked)
                layout.addWidget(card)
                if ti < len(steps) - 1:
                    down = QLabel("↓")
                    down.setObjectName("FlowStepArrow")
                    down.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    layout.addWidget(down)

        add_btn = QPushButton("+ 步骤")
        add_btn.setObjectName("FlowGhostButton")
        add_btn.clicked.connect(lambda _=False, s=stage_idx: self.add_step_requested.emit(s))
        layout.addWidget(add_btn)
        layout.addStretch(1)
        return frame

    def _on_card_clicked(self, stage_idx: int, step_idx: int) -> None:
        self._selected = (stage_idx, step_idx)
        self.selection_changed.emit(stage_idx, step_idx)
        self.render(self._data)
