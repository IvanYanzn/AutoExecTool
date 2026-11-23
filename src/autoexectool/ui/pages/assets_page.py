from __future__ import annotations

import yaml
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.storage.repositories import CommandGroupRepository, VariableSetRepository


class AssetsPage(QWidget):
    """变量集与指令组管理。"""

    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("变量集与指令组")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        tip = QLabel("变量集可在执行时合并；指令组可在流程中通过 use_group 引用。")
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        tabs = QTabWidget()
        tabs.addTab(self._build_varset_tab(), "变量集")
        tabs.addTab(self._build_group_tab(), "指令组")
        layout.addWidget(tabs, 1)

    def _build_varset_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        row = QHBoxLayout()
        self.vs_name = QLineEdit()
        self.vs_name.setPlaceholderText("变量集名称，如 env-dev")
        row.addWidget(self.vs_name, 1)
        btn_save = QPushButton("保存变量集")
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self._save_varset)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_varsets)
        row.addWidget(btn_save)
        row.addWidget(btn_refresh)
        layout.addLayout(row)
        self.vs_editor = QPlainTextEdit()
        self.vs_editor.setPlaceholderText("YAML 字典，例如：\nAPP_ENV: dev\nPORT: 8080\n")
        layout.addWidget(self.vs_editor, 1)
        self.vs_table = QTableWidget(0, 2)
        self.vs_table.setHorizontalHeaderLabels(["名称", "说明"])
        self.vs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.vs_table.cellClicked.connect(self._load_varset_row)
        layout.addWidget(self.vs_table, 1)
        self._refresh_varsets()
        return w

    def _build_group_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        row = QHBoxLayout()
        self.cg_name = QLineEdit()
        self.cg_name.setPlaceholderText("指令组名称，如 greet")
        row.addWidget(self.cg_name, 1)
        btn_save = QPushButton("保存指令组")
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self._save_group)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_groups)
        row.addWidget(btn_save)
        row.addWidget(btn_refresh)
        layout.addLayout(row)
        self.cg_editor = QPlainTextEdit()
        self.cg_editor.setPlaceholderText(
            "YAML，含 steps 列表，例如：\nsteps:\n  - id: say\n    action: shell\n    command: echo hi\n"
        )
        layout.addWidget(self.cg_editor, 1)
        self.cg_table = QTableWidget(0, 2)
        self.cg_table.setHorizontalHeaderLabels(["名称", "说明"])
        self.cg_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cg_table.cellClicked.connect(self._load_group_row)
        layout.addWidget(self.cg_table, 1)
        self._refresh_groups()
        return w

    def _refresh_varsets(self) -> None:
        self.vs_table.setRowCount(0)
        with self.container.session_factory() as session:
            for row in VariableSetRepository(session).list():
                r = self.vs_table.rowCount()
                self.vs_table.insertRow(r)
                self.vs_table.setItem(r, 0, QTableWidgetItem(row.name))
                self.vs_table.setItem(r, 1, QTableWidgetItem(row.description or ""))

    def _refresh_groups(self) -> None:
        self.cg_table.setRowCount(0)
        with self.container.session_factory() as session:
            for row in CommandGroupRepository(session).list():
                r = self.cg_table.rowCount()
                self.cg_table.insertRow(r)
                self.cg_table.setItem(r, 0, QTableWidgetItem(row.name))
                self.cg_table.setItem(r, 1, QTableWidgetItem(row.description or ""))

    def _load_varset_row(self, row: int, _col: int) -> None:
        item = self.vs_table.item(row, 0)
        if not item:
            return
        name = item.text()
        with self.container.session_factory() as session:
            vars_map = VariableSetRepository(session).get_vars(name)
        self.vs_name.setText(name)
        self.vs_editor.setPlainText(yaml.safe_dump(vars_map, allow_unicode=True, sort_keys=False))

    def _load_group_row(self, row: int, _col: int) -> None:
        item = self.cg_table.item(row, 0)
        if not item:
            return
        name = item.text()
        with self.container.session_factory() as session:
            content = CommandGroupRepository(session).get_content(name)
        self.cg_name.setText(name)
        self.cg_editor.setPlainText(yaml.safe_dump(content, allow_unicode=True, sort_keys=False))

    def _save_varset(self) -> None:
        name = self.vs_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写变量集名称。")
            return
        try:
            data = yaml.safe_load(self.vs_editor.toPlainText()) or {}
            if not isinstance(data, dict):
                raise ValueError("变量集内容须为字典")
            with self.container.session_factory() as session:
                VariableSetRepository(session).save(name, data)
            self._refresh_varsets()
            QMessageBox.information(self, "成功", f"已保存变量集：{name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _save_group(self) -> None:
        name = self.cg_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写指令组名称。")
            return
        try:
            data = yaml.safe_load(self.cg_editor.toPlainText()) or {}
            if not isinstance(data, dict):
                raise ValueError("指令组内容须为含 steps 的字典")
            with self.container.session_factory() as session:
                CommandGroupRepository(session).save(name, data)
            self._refresh_groups()
            QMessageBox.information(self, "成功", f"已保存指令组：{name}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))
