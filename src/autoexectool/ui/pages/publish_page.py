from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.publish.service import PublishService


class PublishPage(QWidget):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.svc = PublishService(container)
        self._app_id: str | None = None
        self._env_id: str | None = None
        self._package_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("发布中心")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        tip = QLabel(
            "管理应用 / 环境 / 制品，执行发布与一键回滚。"
            "可先点「准备演示应用」在本机跑通全流程。"
            "内置模板：templates/publish/ 下 publish_dir_*.yaml 及对应 rollback_*.yaml。"
        )
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        row = QHBoxLayout()
        btn_demo = QPushButton("准备演示应用")
        btn_demo.setObjectName("PrimaryButton")
        btn_demo.clicked.connect(self._prepare_demo)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh)
        btn_dry = QPushButton("Dry-run 发布")
        btn_dry.clicked.connect(lambda: self._deploy(True))
        btn_deploy = QPushButton("执行发布")
        btn_deploy.clicked.connect(lambda: self._deploy(False))
        btn_rollback = QPushButton("一键回滚")
        btn_rollback.clicked.connect(self._rollback)
        for b in (btn_demo, btn_refresh, btn_dry, btn_deploy, btn_rollback):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)

        self.info = QLabel("尚未选择应用")
        self.info.setObjectName("MutedLabel")
        layout.addWidget(self.info)

        self.records = QTableWidget(0, 5)
        self.records.setHorizontalHeaderLabels(
            ["时间", "版本", "状态", "备份路径", "摘要"]
        )
        self.records.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.records, 1)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("发布/回滚输出…")
        layout.addWidget(self.output, 1)

        self.refresh()

    def refresh(self) -> None:
        apps = self.svc.list_apps()
        if apps and not self._app_id:
            self._app_id = apps[0].id
            envs = self.svc.list_envs(self._app_id)
            pkgs = self.svc.list_packages(self._app_id)
            self._env_id = envs[0].id if envs else None
            self._package_id = pkgs[0].id if pkgs else None
        if self._app_id:
            app = next((a for a in apps if a.id == self._app_id), None)
            self.info.setText(
                f"应用：{app.name if app else self._app_id} | "
                f"环境：{self._env_id or '-'} | 制品：{self._package_id or '-'} | "
                f"部署目录：{app.deploy_dir if app else '-'}"
            )
        else:
            self.info.setText("暂无应用，请先「准备演示应用」或通过 CLI 创建。")

        self.records.setRowCount(0)
        for rec in self.svc.list_records(self._app_id):
            row = self.records.rowCount()
            self.records.insertRow(row)
            values = [
                str(rec.created_at or ""),
                rec.version,
                rec.status,
                rec.backup_ref,
                rec.summary,
            ]
            for col, val in enumerate(values):
                self.records.setItem(row, col, QTableWidgetItem(val))

    def _prepare_demo(self) -> None:
        try:
            app_id, env_id, package_id = self.svc.ensure_demo_app()
            self._app_id, self._env_id, self._package_id = app_id, env_id, package_id
            self.refresh()
            QMessageBox.information(self, "成功", "演示应用 demo-api / local / 1.0.0 已就绪。")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _require_ids(self) -> bool:
        if not (self._app_id and self._env_id and self._package_id):
            QMessageBox.warning(self, "提示", "请先准备演示应用或选择应用/环境/制品。")
            return False
        return True

    def _deploy(self, dry_run: bool) -> None:
        if not self._require_ids():
            return
        try:
            result = self.svc.deploy(
                app_id=self._app_id,  # type: ignore[arg-type]
                env_id=self._env_id,  # type: ignore[arg-type]
                package_id=self._package_id,  # type: ignore[arg-type]
                dry_run=dry_run,
            )
            self.output.clear()
            if dry_run:
                self.output.appendPlainText("\n".join(result.get("plan") or []))
            else:
                self.output.appendPlainText(str(result))
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "发布失败", str(exc))

    def _rollback(self) -> None:
        if not (self._app_id and self._env_id):
            QMessageBox.warning(self, "提示", "请先有成功发布记录。")
            return
        if (
            QMessageBox.question(self, "确认回滚", "将用最近一次成功发布的备份覆盖部署目录，确定？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            result = self.svc.rollback(app_id=self._app_id, env_id=self._env_id)
            self.output.clear()
            self.output.appendPlainText(str(result))
            self.refresh()
            if result.get("status") == "Succeeded":
                QMessageBox.information(self, "回滚成功", result.get("summary") or "完成")
            else:
                QMessageBox.warning(self, "回滚结束", result.get("summary") or str(result))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "回滚失败", str(exc))
