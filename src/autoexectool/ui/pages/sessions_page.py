from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.application.session_service import SessionService
from autoexectool.orchestrator.timeline import TimelineReader
from autoexectool.ui.widgets.log_console import LogConsole


class SessionsPage(QWidget):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.svc = SessionService(container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("执行记录")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        tip = QLabel(
            "展示落库会话与时间线（类别：会话/阶段/节点/执行/返回/输出）。"
            "Interrupted/Failed 可整单重跑或从失败步骤重跑。"
        )
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        row = QHBoxLayout()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        rerun_full = QPushButton("整单重跑")
        rerun_full.setObjectName("PrimaryButton")
        rerun_full.clicked.connect(lambda: self._rerun(False))
        rerun_failed = QPushButton("从失败步重跑")
        rerun_failed.clicked.connect(lambda: self._rerun(True))
        btn_timeline = QPushButton("重新加载时间线")
        btn_timeline.clicked.connect(self._load_timeline)
        for b in (refresh, rerun_full, rerun_failed, btn_timeline):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "流程", "状态", "触发", "失败步", "摘要"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_layout.addWidget(self.table, 2)

        self.steps = QTableWidget(0, 4)
        self.steps.setHorizontalHeaderLabels(["步骤", "动作", "状态", "消息"])
        self.steps.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_layout.addWidget(QLabel("步骤摘要"))
        left_layout.addWidget(self.steps, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("执行时间线"))
        self.timeline_view = LogConsole()
        self.timeline_view.setPlaceholderText("选中一条会话后，在此查看完整时间线…")
        right_layout.addWidget(self.timeline_view, 1)
        self.timeline_path_label = QLabel("")
        self.timeline_path_label.setObjectName("MutedLabel")
        self.timeline_path_label.setWordWrap(True)
        right_layout.addWidget(self.timeline_path_label)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

        self.table.itemSelectionChanged.connect(self._on_select)
        self.refresh()

    def _timeline_file(self, session_id: str) -> Path:
        return self.container.paths.logs_exec / session_id / "timeline.jsonl"

    def refresh(self) -> None:
        self.table.setRowCount(0)
        for s in self.svc.list_sessions():
            i = self.table.rowCount()
            self.table.insertRow(i)
            vals = [
                s.id,
                s.playbook_name,
                s.status,
                s.trigger,
                s.failed_step_key or "-",
                s.summary,
            ]
            for c, v in enumerate(vals):
                self.table.setItem(i, c, QTableWidgetItem(str(v)))

    def _selected_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).text()

    def _on_select(self) -> None:
        self._load_steps()
        self._load_timeline()

    def _load_steps(self) -> None:
        sid = self._selected_id()
        self.steps.setRowCount(0)
        if not sid:
            return
        for st in self.svc.list_steps(sid):
            i = self.steps.rowCount()
            self.steps.insertRow(i)
            for c, v in enumerate([st.step_key, st.action, st.status, st.message]):
                self.steps.setItem(i, c, QTableWidgetItem(str(v)))

    def _load_timeline(self) -> None:
        sid = self._selected_id()
        self.timeline_view.clear_log()
        if not sid:
            self.timeline_path_label.setText("")
            return
        path = self._timeline_file(sid)
        self.timeline_path_label.setText(str(path))
        if not path.exists():
            self.timeline_view.append_line(
                "该会话尚无 timeline.jsonl（可能为旧记录，仅有步骤摘要与 .out/.err）。",
                "warn",
            )
            # 尝试展示步骤 out 文件摘要
            out_dir = path.parent
            if out_dir.is_dir():
                for f in sorted(out_dir.glob("*.out")):
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if text.strip():
                        self.timeline_view.append_line(f"—— {f.name} ——", "meta")
                        preview = text if len(text) < 4000 else text[:4000] + "\n…"
                        self.timeline_view.append_line(preview, "info")
            return
        reader = TimelineReader(path)
        for event in reader.iter_all():
            self.timeline_view.append_event(event)

    def _rerun(self, from_failed: bool) -> None:
        sid = self._selected_id()
        if not sid:
            QMessageBox.warning(self, "提示", "请先选择一条执行记录。")
            return
        try:
            new_id = self.svc.rerun(sid, from_failed_step=from_failed)
            runtime = self.container.orchestrator.get_status(new_id)
            QMessageBox.information(
                self,
                "重跑完成",
                f"新会话：{new_id}\n状态：{runtime.status}\n摘要：{runtime.summary}",
            )
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "重跑失败", str(exc))
