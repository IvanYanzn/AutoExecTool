from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autoexectool import APP_NAME_EN, APP_NAME_ZH, __version__
from autoexectool.actions.labels import protocol_label
from autoexectool.app.container import AppContainer


class HomePage(QWidget):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel(f"欢迎使用 {APP_NAME_ZH}")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        sub = QLabel(f"{APP_NAME_EN} {__version__} · 通用自动化任务编排与执行")
        sub.setObjectName("MutedLabel")
        layout.addWidget(sub)

        guide = QLabel(
            "建议上手路径：\n"
            "1. 在「执行流程」选择示例模板，先 Dry-run，再本地执行\n"
            "2. 在「流程编排」用画布 / 节点属性 / YAML 编辑自己的流程\n"
            "3. 需要远程时，在「主机与凭证」添加主机；凭证加密见「系统设置 → 安全」\n"
            "4. 发布类场景可到「发布中心」跑演示发布与回滚"
        )
        guide.setObjectName("MutedLabel")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        btn_row = QHBoxLayout()
        for text, idx in (
            ("去执行流程", 1),
            ("去流程编排", 2),
            ("去主机与凭证", 4),
            ("去系统设置", 8),
        ):
            b = QPushButton(text)
            if text == "去执行流程":
                b.setObjectName("PrimaryButton")
            b.clicked.connect(lambda _=False, i=idx: self._goto(i))
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        act_title = QLabel("内置动作（名称 + 代码）")
        act_title.setObjectName("TitleLabel")
        layout.addWidget(act_title)
        tip_a = QLabel("编排 YAML / 节点属性中填写「代码」；下表名称便于识别。")
        tip_a.setObjectName("MutedLabel")
        layout.addWidget(tip_a)

        self.action_table = QTableWidget(0, 3)
        self.action_table.setHorizontalHeaderLabels(["名称", "代码", "适用系统"])
        self.action_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.action_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.action_table.verticalHeader().setVisible(False)
        layout.addWidget(self.action_table, 2)

        proto_title = QLabel("连接协议")
        proto_title.setObjectName("TitleLabel")
        layout.addWidget(proto_title)
        self.proto_table = QTableWidget(0, 2)
        self.proto_table.setHorizontalHeaderLabels(["名称", "代码"])
        self.proto_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.proto_table.verticalHeader().setVisible(False)
        layout.addWidget(self.proto_table, 1)

        self._fill_tables()

    def _goto(self, index: int) -> None:
        win = self.window()
        if hasattr(win, "_goto"):
            win._goto(index)  # type: ignore[attr-defined]

    def _fill_tables(self) -> None:
        os_map = {"any": "通用", "windows": "Windows", "linux": "Linux"}
        rows = self.container.actions.catalog(include_aliases=False)
        self.action_table.setRowCount(0)
        for item in rows:
            r = self.action_table.rowCount()
            self.action_table.insertRow(r)
            self.action_table.setItem(r, 0, QTableWidgetItem(item["name"]))
            self.action_table.setItem(r, 1, QTableWidgetItem(item["code"]))
            self.action_table.setItem(
                r, 2, QTableWidgetItem(os_map.get(item["os"], item["os"]))
            )
        self.action_table.resizeColumnsToContents()

        self.proto_table.setRowCount(0)
        for code in self.container.connectors.protocols():
            r = self.proto_table.rowCount()
            self.proto_table.insertRow(r)
            self.proto_table.setItem(r, 0, QTableWidgetItem(protocol_label(code)))
            self.proto_table.setItem(r, 1, QTableWidgetItem(code))
        self.proto_table.resizeColumnsToContents()
