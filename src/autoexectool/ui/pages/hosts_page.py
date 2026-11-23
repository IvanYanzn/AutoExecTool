from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.application.host_service import HostService


class HostsPage(QWidget):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.svc = HostService(container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("主机与凭证")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        tip = QLabel(
            "远程凭证需主密码加密（系统设置 → 安全）。\n"
            "· 方案 B（工具内上传）：保存「密码」凭证并「绑定」到主机即可。\n"
            "· 方案 A（本机 ssh/scp 一键编排）：需「配置本机OpenSSH免密」"
            "（把本机 ~/.ssh 公钥装到服务器）。"
        )
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        unlock_row = QHBoxLayout()
        self.unlock_btn = QPushButton("解锁保险库")
        self.unlock_btn.setObjectName("PrimaryButton")
        self.unlock_btn.clicked.connect(self._unlock)
        self.unlock_label = QLabel("")
        self.unlock_label.setObjectName("MutedLabel")
        unlock_row.addWidget(self.unlock_btn)
        unlock_row.addWidget(self.unlock_label)
        unlock_row.addStretch(1)
        layout.addLayout(unlock_row)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["local", "ssh", "winrm"])
        self.os_combo = QComboBox()
        self.os_combo.addItems(["windows", "linux"])
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("默认：ssh=22 / winrm=5985")
        form.addRow("名称", self.name_edit)
        form.addRow("地址", self.address_edit)
        form.addRow("协议", self.protocol_combo)
        form.addRow("系统", self.os_combo)
        form.addRow("端口", self.port_edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("保存主机")
        add_btn.clicked.connect(self._add_host)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        test_btn = QPushButton("测试选中连接")
        test_btn.clicked.connect(self._test_selected)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(test_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "名称", "协议", "地址", "端口", "系统"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        cred_title = QLabel("凭证（加密存储）")
        cred_title.setObjectName("TitleLabel")
        layout.addWidget(cred_title)
        cred_form = QFormLayout()
        self.cred_name = QLineEdit()
        self.cred_user = QLineEdit()
        self.cred_pass = QLineEdit()
        self.cred_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.cred_pass.setPlaceholderText("修改时留空表示不改密码")
        self.cred_edit_hint = QLabel("当前：新建凭证")
        self.cred_edit_hint.setObjectName("MutedLabel")
        cred_form.addRow("凭证名", self.cred_name)
        cred_form.addRow("用户名", self.cred_user)
        cred_form.addRow("密码", self.cred_pass)
        cred_form.addRow("", self.cred_edit_hint)
        layout.addLayout(cred_form)
        self._editing_cred_id: str | None = None
        self._editing_cred_auth: str = "password"

        def _btn(text: str, tip_text: str, slot) -> QPushButton:
            b = QPushButton(text)
            b.setToolTip(tip_text)
            b.clicked.connect(slot)
            return b

        cred_btn_row1 = QHBoxLayout()
        for b in (
            _btn(
                "保存密码凭证",
                "新建或更新「密码」类型凭证（同 Xshell 账号密码）。\n"
                "修改时：先载入，密码留空表示不改原密码。",
                self._save_cred,
            ),
            _btn(
                "载入修改",
                "把选中凭证的名称/用户名载入上方表单，便于修改后保存。",
                self._load_selected_cred,
            ),
            _btn(
                "删除选中凭证",
                "删除选中凭证；已绑定该凭证的主机将自动解除绑定。",
                self._delete_selected_cred,
            ),
            _btn("清空表单", "清空上方输入，准备新建凭证。", self._clear_cred_form),
            _btn(
                "绑定选中凭证到主机",
                "仅在本工具内记录：选中主机以后用选中凭证登录。\n"
                "用于方案 B / 测试连接；不影响本机 OpenSSH（方案 A）。",
                self._bind_credential,
            ),
        ):
            cred_btn_row1.addWidget(b)
        cred_btn_row1.addStretch(1)
        layout.addLayout(cred_btn_row1)

        cred_btn_row2 = QHBoxLayout()
        for b in (
            _btn(
                "生成SSH密钥凭证",
                "生成工具内 Ed25519 密钥：私钥加密存保险库，公钥写入 data/config/keys/。\n"
                "供方案 B（Paramiko）使用，不是本机 OpenSSH 的默认密钥。",
                self._generate_ssh_key,
            ),
            _btn(
                "复制选中公钥",
                "复制选中「密钥凭证」的公钥到剪贴板，可手工发给管理员。",
                self._copy_selected_public_key,
            ),
            _btn(
                "安装公钥到选中主机",
                "用密码登录选中主机，把选中「密钥凭证」的公钥写入 authorized_keys，\n"
                "并自动绑定该密钥凭证。用于方案 B 免密，不是方案 A。",
                self._install_public_key,
            ),
            _btn(
                "配置本机OpenSSH免密",
                "【方案 A 专用】确保本机 %USERPROFILE%\\.ssh\\id_ed25519 存在，\n"
                "并用密码凭证把该公钥装到选中主机。\n"
                "完成后本机 ssh/scp（方案 A 类编排）才能免密执行。",
                self._setup_openssh_passwordless,
            ),
        ):
            cred_btn_row2.addWidget(b)
        cred_btn_row2.addStretch(1)
        layout.addLayout(cred_btn_row2)

        cred_help = QLabel(
            "按钮说明（鼠标悬停按钮也可看提示）：\n"
            "· 保存/载入/删除/清空：管理密码或密钥凭证本身。\n"
            "· 绑定选中凭证到主机：只改工具内关联，给「测试连接 / 方案 B」用。\n"
            "· 生成SSH密钥凭证 / 复制公钥 / 安装公钥到选中主机：工具内密钥体系（方案 B）。\n"
            "· 配置本机OpenSSH免密：给方案 A（本机 ssh/scp 一键编排）用；"
            "需已有密码凭证，选中目标 SSH 主机后点击。"
        )
        cred_help.setObjectName("MutedLabel")
        cred_help.setWordWrap(True)
        layout.addWidget(cred_help)

        self.cred_table = QTableWidget(0, 3)
        self.cred_table.setHorizontalHeaderLabels(["ID", "名称", "类型"])
        self.cred_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cred_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cred_table.itemSelectionChanged.connect(self._on_cred_selection_changed)
        self.cred_table.cellDoubleClicked.connect(lambda *_: self._load_selected_cred())
        layout.addWidget(self.cred_table, 1)

        group_title = QLabel("主机组")
        group_title.setObjectName("TitleLabel")
        layout.addWidget(group_title)
        gform = QFormLayout()
        self.group_name = QLineEdit()
        self.group_name.setPlaceholderText("组名，如 web-prod")
        gform.addRow("组名", self.group_name)
        layout.addLayout(gform)
        grow = QHBoxLayout()
        save_group = QPushButton("保存组（含当前选中主机）")
        save_group.clicked.connect(self._save_group)
        del_group = QPushButton("删除选中组")
        del_group.clicked.connect(self._delete_group)
        grow.addWidget(save_group)
        grow.addWidget(del_group)
        grow.addStretch(1)
        layout.addLayout(grow)
        self.group_table = QTableWidget(0, 3)
        self.group_table.setHorizontalHeaderLabels(["ID", "名称", "成员数"])
        self.group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.group_table, 1)

        self.refresh()
        self._refresh_unlock_label()

    def _refresh_unlock_label(self) -> None:
        mk = self.container.master_keys
        if not mk.is_initialized:
            self.unlock_label.setText("未设置（请到 系统设置 → 安全）")
        elif mk.is_unlocked:
            self.unlock_label.setText("本会话已解锁")
        else:
            self.unlock_label.setText("已锁定")

    def _unlock(self) -> None:
        from autoexectool.ui.dialogs.master_password import prompt_unlock_master

        prompt_unlock_master(self, self.container.master_keys)
        self._refresh_unlock_label()

    def refresh(self) -> None:
        hosts = self.svc.list_hosts()
        self.table.setRowCount(0)
        for h in hosts:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                h.id,
                h.name,
                h.protocol.value,
                h.address,
                str(h.port),
                h.os_type.value,
            ]
            for col, val in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(val))

        self.cred_table.setRowCount(0)
        for cid, name, auth_type in self.svc.list_credentials():
            row = self.cred_table.rowCount()
            self.cred_table.insertRow(row)
            for col, val in enumerate([cid, name, auth_type]):
                self.cred_table.setItem(row, col, QTableWidgetItem(val))

        self.group_table.setRowCount(0)
        for g in self.svc.list_host_groups():
            row = self.group_table.rowCount()
            self.group_table.insertRow(row)
            for col, val in enumerate([g.id, g.name, str(len(g.host_ids))]):
                self.group_table.setItem(row, col, QTableWidgetItem(val))

    def _selected_host_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.text() if item else None

    def _add_host(self) -> None:
        try:
            port_text = self.port_edit.text().strip()
            host = self.svc.upsert_host(
                name=self.name_edit.text().strip(),
                address=self.address_edit.text().strip(),
                protocol=self.protocol_combo.currentText(),
                os_type=self.os_combo.currentText(),
                port=int(port_text) if port_text else None,
            )
            QMessageBox.information(self, "成功", f"已保存主机：{host.name}")
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _test_selected(self) -> None:
        host_id = self._selected_host_id()
        if not host_id:
            QMessageBox.warning(self, "提示", "请先选中一台主机。")
            return
        try:
            host = next((h for h in self.svc.list_hosts() if h.id == host_id), None)
            if host and host.credential_id and not self.container.master_keys.is_unlocked:
                from autoexectool.ui.dialogs.master_password import prompt_unlock_master

                if not prompt_unlock_master(self, self.container.master_keys):
                    return
                self._refresh_unlock_label()
            msg = self.svc.test_connection(host_id)
            QMessageBox.information(self, "连接成功", msg)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "连接失败", str(exc))

    def _delete_selected(self) -> None:
        host_id = self._selected_host_id()
        if not host_id:
            return
        if QMessageBox.question(self, "确认", "确定删除该主机？") != QMessageBox.StandardButton.Yes:
            return
        self.svc.delete_host(host_id)
        self.refresh()

    def _ensure_vault(self) -> bool:
        from autoexectool.ui.dialogs.master_password import (
            prompt_initialize_master,
            prompt_unlock_master,
        )

        mk = self.container.master_keys
        if not mk.is_initialized:
            if not prompt_initialize_master(self, mk):
                return False
            self._refresh_unlock_label()
            return True
        if not mk.is_unlocked:
            if not prompt_unlock_master(self, mk):
                return False
            self._refresh_unlock_label()
        return True

    def _selected_cred_id(self) -> str | None:
        rows = self.cred_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.cred_table.item(rows[0].row(), 0)
        return item.text() if item else None

    def _clear_cred_form(self) -> None:
        self._editing_cred_id = None
        self._editing_cred_auth = "password"
        self.cred_name.clear()
        self.cred_user.clear()
        self.cred_pass.clear()
        self.cred_edit_hint.setText("当前：新建凭证")

    def _on_cred_selection_changed(self) -> None:
        # 仅提示，不自动载入密码，避免误覆盖表单
        cred_id = self._selected_cred_id()
        if not cred_id:
            return
        name_item = None
        rows = self.cred_table.selectionModel().selectedRows()
        if rows:
            name_item = self.cred_table.item(rows[0].row(), 1)
            type_item = self.cred_table.item(rows[0].row(), 2)
            auth = type_item.text() if type_item else ""
            self.cred_edit_hint.setText(
                f"已选中：{name_item.text() if name_item else cred_id}（{auth}）。"
                "点「载入修改」或双击载入；改完后点「保存密码凭证」。"
            )

    def _load_selected_cred(self) -> None:
        cred_id = self._selected_cred_id()
        if not cred_id:
            QMessageBox.warning(self, "提示", "请先选中一条凭证。")
            return
        if not self._ensure_vault():
            return
        try:
            cred = self.svc.get_credential(cred_id)
            self._editing_cred_id = cred.id
            self._editing_cred_auth = cred.auth_type
            self.cred_name.setText(cred.name)
            self.cred_user.setText(cred.username)
            self.cred_pass.clear()
            if cred.auth_type == "ssh_key":
                self.cred_edit_hint.setText(
                    f"当前：修改密钥凭证 {cred.name}（密码栏对密钥凭证无效；私钥保留在库中）"
                )
            else:
                self.cred_edit_hint.setText(
                    f"当前：修改密码凭证 {cred.name}（密码留空则保持原密码）"
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _delete_selected_cred(self) -> None:
        cred_id = self._selected_cred_id()
        if not cred_id:
            QMessageBox.warning(self, "提示", "请先选中一条凭证。")
            return
        if not self._ensure_vault():
            return
        name = ""
        rows = self.cred_table.selectionModel().selectedRows()
        if rows:
            item = self.cred_table.item(rows[0].row(), 1)
            name = item.text() if item else cred_id
        if (
            QMessageBox.question(
                self,
                "确认删除",
                f"确定删除凭证「{name or cred_id}」？\n绑定该凭证的主机将解除绑定。",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.svc.delete_credential(cred_id)
            if self._editing_cred_id == cred_id:
                self._clear_cred_form()
            QMessageBox.information(self, "成功", "凭证已删除。")
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _save_cred(self) -> None:
        if not self._ensure_vault():
            return
        name = self.cred_name.text().strip()
        user = self.cred_user.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写凭证名。")
            return
        if self._editing_cred_id and self._editing_cred_auth == "ssh_key":
            # 密钥凭证允许改名称/用户名，不走密码覆盖
            try:
                cred = self.svc.save_credential(
                    name=name,
                    auth_type="ssh_key",
                    username=user,
                    credential_id=self._editing_cred_id,
                    keep_password_if_empty=True,
                )
                QMessageBox.information(self, "成功", f"已更新密钥凭证：{cred.name}")
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "失败", str(exc))
            return
        password = self.cred_pass.text()
        if not self._editing_cred_id and not password:
            QMessageBox.warning(self, "提示", "新建密码凭证时请填写密码。")
            return
        try:
            cred = self.svc.save_credential(
                name=name,
                auth_type="password",
                username=user,
                password=password,
                credential_id=self._editing_cred_id,
                keep_password_if_empty=True,
            )
            action = "已更新" if self._editing_cred_id else "已保存"
            QMessageBox.information(self, "成功", f"{action}密码凭证：{cred.name}")
            self.cred_pass.clear()
            self._editing_cred_id = cred.id
            self._editing_cred_auth = "password"
            self.cred_edit_hint.setText(f"当前：修改密码凭证 {cred.name}（密码留空则保持原密码）")
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _generate_ssh_key(self) -> None:
        if not self._ensure_vault():
            return
        name = self.cred_name.text().strip() or "ssh-key"
        user = self.cred_user.text().strip()
        if not user:
            QMessageBox.warning(self, "提示", "请先填写用户名（如 deploy）。")
            return
        try:
            cred, pub_path, public_line = self.svc.generate_ssh_key_credential(
                name=name,
                username=user,
                comment=f"autoexectool:{name}",
            )
            QGuiApplication.clipboard().setText(public_line)
            QMessageBox.information(
                self,
                "已生成密钥",
                f"凭证：{cred.name}（类型 ssh_key）\n"
                f"公钥文件：{pub_path}\n"
                f"公钥已复制到剪贴板。\n\n"
                "私钥仅加密保存在保险库，不会明文写入程序目录。\n"
                "可将公钥交给管理员写入 authorized_keys，"
                "或先保存密码凭证后点「安装公钥到选中主机」。",
            )
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _copy_selected_public_key(self) -> None:
        cred_id = self._selected_cred_id()
        if not cred_id:
            QMessageBox.warning(self, "提示", "请先在凭证表中选中一条密钥凭证。")
            return
        if not self._ensure_vault():
            return
        try:
            line, path = self.svc.get_credential_public_key(cred_id)
            QGuiApplication.clipboard().setText(line)
            QMessageBox.information(
                self,
                "已复制",
                f"公钥已复制到剪贴板。\n文件：{path or '（内存导出）'}",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _install_public_key(self) -> None:
        host_id = self._selected_host_id()
        key_id = self._selected_cred_id()
        if not host_id:
            QMessageBox.warning(self, "提示", "请先选中一台 SSH 主机。")
            return
        if not key_id:
            QMessageBox.warning(self, "提示", "请先选中一条密钥凭证（类型 ssh_key）。")
            return
        if not self._ensure_vault():
            return
        # 若主机尚未绑密码，尝试用凭证表里另一条 password 类型
        password_id = None
        host = next((h for h in self.svc.list_hosts() if h.id == host_id), None)
        if host and host.credential_id and host.credential_id != key_id:
            password_id = host.credential_id
        else:
            for cid, _name, auth_type in self.svc.list_credentials():
                if auth_type == "password" and cid != key_id:
                    password_id = cid
                    break
        if not password_id:
            QMessageBox.warning(
                self,
                "提示",
                "安装公钥需要先有一条「密码」凭证（与 Xshell 相同账号密码）。\n"
                "请先保存密码凭证，并绑定到该主机，或保证凭证列表中有密码凭证。",
            )
            return
        try:
            msg = self.svc.install_public_key_to_host(
                host_id=host_id,
                key_credential_id=key_id,
                password_credential_id=password_id,
            )
            QMessageBox.information(self, "安装成功", msg)
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "安装失败", str(exc))

    def _bind_credential(self) -> None:
        host_id = self._selected_host_id()
        cred_id = self._selected_cred_id()
        if not host_id or not cred_id:
            QMessageBox.warning(self, "提示", "请同时选中一台主机和一条凭证。")
            return
        try:
            host = self.svc.bind_credential(host_id, cred_id)
            QMessageBox.information(
                self, "成功", f"已将凭证绑定到主机「{host.name}」。"
            )
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _setup_openssh_passwordless(self) -> None:
        host_id = self._selected_host_id()
        if not host_id:
            QMessageBox.warning(
                self,
                "提示",
                "请先选中一台 SSH 主机。\n"
                "并确保已有「密码」凭证（建议先绑定到该主机）。",
            )
            return
        if not self._ensure_vault():
            return
        password_id = self._selected_cred_id()
        # 若选中的不是密码凭证，交给服务层自动查找
        if password_id:
            rows = self.cred_table.selectionModel().selectedRows()
            auth = ""
            if rows:
                item = self.cred_table.item(rows[0].row(), 2)
                auth = item.text() if item else ""
            if auth != "password":
                password_id = None
        try:
            msg = self.svc.setup_openssh_passwordless(
                host_id=host_id,
                password_credential_id=password_id,
            )
            QMessageBox.information(self, "本机 OpenSSH 免密已配置", msg)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "配置失败", str(exc))

    def _selected_host_ids(self) -> list[str]:
        rows = self.table.selectionModel().selectedRows()
        ids: list[str] = []
        for r in rows:
            item = self.table.item(r.row(), 0)
            if item:
                ids.append(item.text())
        return ids

    def _save_group(self) -> None:
        name = self.group_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写组名。")
            return
        host_ids = self._selected_host_ids()
        if not host_ids:
            QMessageBox.warning(self, "提示", "请在主机表中选中至少一台成员主机。")
            return
        try:
            g = self.svc.upsert_host_group(name=name, host_ids=host_ids)
            QMessageBox.information(self, "成功", f"已保存主机组：{g.name}（{len(g.host_ids)} 台）")
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _delete_group(self) -> None:
        rows = self.group_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.group_table.item(rows[0].row(), 0)
        if not item:
            return
        if QMessageBox.question(self, "确认", "确定删除该主机组？") != QMessageBox.StandardButton.Yes:
            return
        self.svc.delete_host_group(item.text())
        self.refresh()
