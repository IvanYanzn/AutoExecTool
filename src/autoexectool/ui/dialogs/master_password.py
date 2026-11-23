from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from autoexectool.security.crypto import MasterKeyManager


def prompt_initialize_master(parent: QWidget, master_keys: MasterKeyManager) -> bool:
    """在界面内初始化主密码；成功返回 True。"""
    if master_keys.is_initialized:
        QMessageBox.information(parent, "提示", "主密码已初始化，无需重复设置。")
        return True
    pwd1, ok1 = QInputDialog.getText(
        parent,
        "设置主密码",
        "请设置主密码（用于加密远程凭证，请妥善保管）：",
        QLineEdit.EchoMode.Password,
    )
    if not ok1 or not pwd1:
        return False
    if len(pwd1) < 4:
        QMessageBox.warning(parent, "提示", "主密码至少 4 位。")
        return False
    pwd2, ok2 = QInputDialog.getText(
        parent,
        "确认主密码",
        "请再输入一次主密码：",
        QLineEdit.EchoMode.Password,
    )
    if not ok2 or pwd2 != pwd1:
        QMessageBox.warning(parent, "提示", "两次输入不一致。")
        return False
    try:
        master_keys.initialize(pwd1)
        QMessageBox.information(parent, "成功", "主密码已设置，当前会话已解锁。")
        return True
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(parent, "失败", str(exc))
        return False


def prompt_unlock_master(parent: QWidget, master_keys: MasterKeyManager) -> bool:
    """解锁主密码；未初始化时引导先设置。"""
    if not master_keys.is_initialized:
        go = QMessageBox.question(
            parent,
            "尚未设置主密码",
            "保存加密凭证前需要先设置主密码。\n是否现在设置？",
        )
        if go != QMessageBox.StandardButton.Yes:
            return False
        return prompt_initialize_master(parent, master_keys)
    if master_keys.is_unlocked:
        QMessageBox.information(parent, "提示", "保险库已解锁。")
        return True
    text, ok = QInputDialog.getText(
        parent, "解锁", "请输入主密码：", QLineEdit.EchoMode.Password
    )
    if not ok or not text:
        return False
    try:
        master_keys.unlock(text)
        QMessageBox.information(parent, "成功", "主密码已解锁。")
        return True
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(parent, "失败", str(exc))
        return False
