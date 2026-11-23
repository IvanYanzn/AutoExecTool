from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from autoexectool import APP_NAME_EN, APP_NAME_ZH, __version__
from autoexectool.app.container import AppContainer
from autoexectool.application.backup_service import BackupService
from autoexectool.application.log_cleanup import LogCleanupService


class SettingsPage(QWidget):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.backup = BackupService(container)
        self.cleanup = LogCleanupService(container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("系统设置")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        # —— 关于 ——
        layout.addWidget(self._section_title("关于"))
        layout.addWidget(QLabel(f"产品：{APP_NAME_ZH}（{APP_NAME_EN}）"))
        layout.addWidget(QLabel(f"版本：{__version__}"))
        layout.addWidget(QLabel(f"数据目录：{container.paths.root}"))
        layout.addWidget(
            QLabel(f"已加载插件：{', '.join(container.loaded_plugins) or '无'}")
        )
        act_lines = [
            f"{r['name']}（{r['code']}）" for r in container.actions.catalog()
        ]
        act_lbl = QLabel("已注册动作：\n" + "\n".join(act_lines))
        act_lbl.setWordWrap(True)
        act_lbl.setObjectName("MutedLabel")
        layout.addWidget(act_lbl)

        # —— 安全（主密码唯一主入口）——
        layout.addWidget(self._section_title("安全"))
        tip = QLabel(
            "主密码用于加密存储远程主机凭证，不是登录本程序的账号密码。"
            "仅在需要保存/使用远程凭证时设置；本地执行可不设置。"
            "请妥善保管，丢失后已存凭证无法解密。"
        )
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.vault_label = QLabel("")
        self.vault_label.setObjectName("MutedLabel")
        layout.addWidget(self.vault_label)

        vault_row = QHBoxLayout()
        self.btn_init = QPushButton("设置主密码")
        self.btn_init.setObjectName("PrimaryButton")
        self.btn_init.clicked.connect(self._init_master)
        self.btn_unlock = QPushButton("解锁保险库")
        self.btn_unlock.clicked.connect(self._unlock_master)
        self.btn_lock = QPushButton("锁定保险库")
        self.btn_lock.clicked.connect(self._lock_master)
        vault_row.addWidget(self.btn_init)
        vault_row.addWidget(self.btn_unlock)
        vault_row.addWidget(self.btn_lock)
        vault_row.addStretch(1)
        layout.addLayout(vault_row)
        self._refresh_vault_label()

        # —— 数据与维护 ——
        layout.addWidget(self._section_title("数据与维护"))
        row = QHBoxLayout()
        btn_backup = QPushButton("备份 data")
        btn_backup.clicked.connect(self._backup)
        btn_restore = QPushButton("从 zip 恢复…")
        btn_restore.clicked.connect(self._restore)
        row.addWidget(btn_backup)
        row.addWidget(btn_restore)
        row.addStretch(1)
        layout.addLayout(row)

        clean_row = QHBoxLayout()
        self.retain_days = QSpinBox()
        self.retain_days.setRange(1, 3650)
        self.retain_days.setValue(30)
        self.retain_days.setSuffix(" 天")
        btn_clean = QPushButton("清理过期日志")
        btn_clean.clicked.connect(self._cleanup_logs)
        clean_row.addWidget(QLabel("日志保留"))
        clean_row.addWidget(self.retain_days)
        clean_row.addWidget(btn_clean)
        clean_row.addStretch(1)
        layout.addLayout(clean_row)
        layout.addStretch(1)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("TitleLabel")
        return lbl

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._refresh_vault_label()

    def _refresh_vault_label(self) -> None:
        mk = self.container.master_keys
        if not mk.is_initialized:
            self.vault_label.setText("状态：未设置主密码")
            self.btn_init.setEnabled(True)
            self.btn_unlock.setEnabled(False)
            self.btn_lock.setEnabled(False)
        elif mk.is_unlocked:
            self.vault_label.setText("状态：已设置 · 本会话已解锁")
            self.btn_init.setEnabled(False)
            self.btn_unlock.setEnabled(False)
            self.btn_lock.setEnabled(True)
        else:
            self.vault_label.setText("状态：已设置 · 本会话已锁定（使用远程凭证前请解锁）")
            self.btn_init.setEnabled(False)
            self.btn_unlock.setEnabled(True)
            self.btn_lock.setEnabled(False)

    def _init_master(self) -> None:
        from autoexectool.ui.dialogs.master_password import prompt_initialize_master

        prompt_initialize_master(self, self.container.master_keys)
        self._refresh_vault_label()

    def _unlock_master(self) -> None:
        from autoexectool.ui.dialogs.master_password import prompt_unlock_master

        prompt_unlock_master(self, self.container.master_keys)
        self._refresh_vault_label()

    def _lock_master(self) -> None:
        self.container.master_keys.lock()
        self._refresh_vault_label()
        QMessageBox.information(self, "已锁定", "保险库已锁定。再次使用远程凭证前请解锁。")

    def _backup(self) -> None:
        try:
            path = self.backup.create_backup()
            QMessageBox.information(self, "备份成功", str(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "备份失败", str(exc))

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择备份 zip",
            str(self.container.paths.backups),
            "ZIP (*.zip)",
        )
        if not path:
            return
        if (
            QMessageBox.question(self, "确认", "将覆盖当前 config/db，确定恢复？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.backup.restore_backup(Path(path))
            QMessageBox.information(self, "完成", "已恢复，建议重启应用。")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "恢复失败", str(exc))

    def _cleanup_logs(self) -> None:
        try:
            result = self.cleanup.cleanup(self.retain_days.value())
            QMessageBox.information(
                self,
                "完成",
                f"已清理目录 {result['dirs']} 个，文件 {result['files']} 个。",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "清理失败", str(exc))
