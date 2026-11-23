from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from croniter import croniter
from PySide6.QtCore import QDateTime, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.application.host_service import HostService
from autoexectool.runtime_paths import playbooks_dir, templates_dir

_WEEKDAY_LABELS = [
    ("周日", 0),
    ("周一", 1),
    ("周二", 2),
    ("周三", 3),
    ("周四", 4),
    ("周五", 5),
    ("周六", 6),
]


def default_once_at() -> datetime:
    """默认：今天本地 17:30；若已过则改为明天 17:30。"""
    now = datetime.now().astimezone()
    target = now.replace(hour=17, minute=30, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target


def _local_tz():
    return datetime.now().astimezone().tzinfo


def _qdt_from_local(dt: datetime) -> QDateTime:
    """QDateTimeEdit 只用「本地墙钟」naive，避免 Qt 再做时区换算。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return QDateTime(dt)


def _local_from_qdt(qdt: QDateTime) -> datetime:
    """控件时间 → 带本地 tz 的 datetime。"""
    py = qdt.toPython()
    if not isinstance(py, datetime):
        raise ValueError("无效的执行时间")
    if py.tzinfo is None:
        return py.replace(tzinfo=_local_tz())
    return py.astimezone()


def _local_from_db(dt: datetime) -> datetime:
    """库内时刻 → 本地。naive 按 UTC（与 SchedulerService 存库约定一致）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def humanize_cron(expr: str) -> str:
    """把常见 Cron 转成中文说明；认不出则原样返回。"""
    expr = (expr or "").strip()
    if not expr:
        return "—"
    m = re.fullmatch(r"\*/(\d+) \* \* \* \*", expr)
    if m:
        return f"每 {m.group(1)} 分钟"
    m = re.fullmatch(r"0 \*/(\d+) \* \* \*", expr)
    if m:
        return f"每 {m.group(1)} 小时"
    m = re.fullmatch(r"(\d+) (\d+) \* \* \*", expr)
    if m:
        return f"每天 {int(m.group(2)):02d}:{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d+) (\d+) \* \* 1-5", expr)
    if m:
        return f"工作日 {int(m.group(2)):02d}:{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d+) (\d+) \* \* ([0-6])", expr)
    if m:
        names = {d: n for n, d in _WEEKDAY_LABELS}
        return f"每{names.get(int(m.group(3)), m.group(3))} {int(m.group(2)):02d}:{int(m.group(1)):02d}"
    return expr


def detect_freq_from_cron(expr: str) -> tuple[str, dict]:
    """从 Cron 反推频率 UI 状态；(freq_key, params)。"""
    expr = (expr or "").strip()
    m = re.fullmatch(r"\*/(\d+) \* \* \* \*", expr)
    if m:
        return "interval", {"every": int(m.group(1)), "unit": "minute"}
    m = re.fullmatch(r"0 \*/(\d+) \* \* \*", expr)
    if m:
        return "interval", {"every": int(m.group(1)), "unit": "hour"}
    m = re.fullmatch(r"(\d+) (\d+) \* \* \*", expr)
    if m:
        return "daily", {"minute": int(m.group(1)), "hour": int(m.group(2))}
    m = re.fullmatch(r"(\d+) (\d+) \* \* 1-5", expr)
    if m:
        return "weekdays", {"minute": int(m.group(1)), "hour": int(m.group(2))}
    m = re.fullmatch(r"(\d+) (\d+) \* \* ([0-6])", expr)
    if m:
        return "weekly", {
            "minute": int(m.group(1)),
            "hour": int(m.group(2)),
            "dow": int(m.group(3)),
        }
    return "cron", {"cron": expr}


class SchedulePage(QWidget):
    """流程级调度：仅一次 / 间隔 / 频率预设 / 自定义 Cron。"""

    DEFAULT_CRON = "30 17 * * *"

    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.host_svc = HostService(container)
        self._editing_id: str | None = None
        self._syncing_freq = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("任务调度")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        tip = QLabel(
            "定时触发「整份流程」（本机本地时区）。"
            "可选手动选「仅一次 / 按间隔 / 每天 / 工作日 / 每周」，不必手写 Cron；"
            "需要复杂规则时再选「自定义 Cron」。"
            "\n"
            "支持多条调度同时启用；同一时刻到期会并行执行。"
            "执行记录与时间线日志与手动执行相同（触发方式为 schedule）。"
            "节点内等到点请用 YAML 的 schedule.execute_at。"
        )
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        form = QFormLayout()
        self._form = form
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如 nightly-deploy")

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("仅一次（到点执行后停用）", "once")
        self.mode_combo.addItem("按间隔重复", "interval")
        self.mode_combo.addItem("每天固定时刻", "daily")
        self.mode_combo.addItem("工作日固定时刻", "weekdays")
        self.mode_combo.addItem("每周固定时刻", "weekly")
        self.mode_combo.addItem("自定义 Cron", "cron")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        # 仅一次
        self.run_at_edit = QDateTimeEdit()
        self.run_at_edit.setCalendarPopup(True)
        self.run_at_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.run_at_edit.setTimeSpec(Qt.TimeSpec.LocalTime)
        self.run_at_edit.setDateTime(_qdt_from_local(default_once_at()))
        self.run_at_edit.dateTimeChanged.connect(lambda *_: self._refresh_hint())

        # 按间隔
        interval_row = QHBoxLayout()
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(5)
        self.interval_unit = QComboBox()
        self.interval_unit.addItem("分钟", "minute")
        self.interval_unit.addItem("小时", "hour")
        self.interval_spin.valueChanged.connect(self._on_freq_changed)
        self.interval_unit.currentIndexChanged.connect(self._on_freq_changed)
        interval_row.addWidget(QLabel("每隔"))
        interval_row.addWidget(self.interval_spin)
        interval_row.addWidget(self.interval_unit)
        interval_row.addStretch(1)
        self.interval_wrap = QWidget()
        self.interval_wrap.setLayout(interval_row)

        # 每天 / 工作日 / 每周 的时刻
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(17, 30))
        self.time_edit.timeChanged.connect(self._on_freq_changed)

        self.weekday_combo = QComboBox()
        for label, val in _WEEKDAY_LABELS:
            self.weekday_combo.addItem(label, val)
        self.weekday_combo.setCurrentIndex(self.weekday_combo.findData(1))  # 周一
        self.weekday_combo.currentIndexChanged.connect(self._on_freq_changed)

        # 自定义 / 生成结果 Cron（只读展示 + 自定义时可编辑）
        self.cron_edit = QLineEdit(self.DEFAULT_CRON)
        self.cron_edit.setPlaceholderText("分 时 日 月 周，例如 */5 * * * *")
        self.cron_edit.textChanged.connect(self._on_cron_edited)

        self.time_hint = QLabel("")
        self.time_hint.setObjectName("MutedLabel")
        self.time_hint.setWordWrap(True)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择要定时执行的流程 YAML…")
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)

        self.host_combo = QComboBox()
        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)
        self.edit_hint = QLabel("当前：新建调度")
        self.edit_hint.setObjectName("MutedLabel")

        form.addRow("名称", self.name_edit)
        form.addRow("类型", self.mode_combo)
        form.addRow("执行时间", self.run_at_edit)
        form.addRow("间隔", self.interval_wrap)
        form.addRow("时刻", self.time_edit)
        form.addRow("星期", self.weekday_combo)
        form.addRow("Cron", self.cron_edit)
        form.addRow("", self.time_hint)
        form.addRow("流程", path_row)
        form.addRow("默认主机", self.host_combo)
        form.addRow("", self.enabled_check)
        form.addRow("", self.edit_hint)
        layout.addLayout(form)

        row = QHBoxLayout()
        save_btn = QPushButton("保存调度")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save)
        new_btn = QPushButton("新建")
        new_btn.clicked.connect(self._clear_form)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        toggle_btn = QPushButton("启用/停用选中")
        toggle_btn.clicked.connect(self._toggle_enabled)
        tick_btn = QPushButton("立即扫描一次")
        tick_btn.setToolTip("立即检查是否有到期任务并触发（不等后台轮询）")
        tick_btn.clicked.connect(self._tick)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._delete)
        for b in (save_btn, new_btn, refresh_btn, toggle_btn, tick_btn, del_btn):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "名称",
                "类型",
                "计划",
                "启用",
                "默认主机",
                "上次运行",
                "上次状态",
                "流程",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnHidden(0, True)
        self.table.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.table, 1)

        self._reload_hosts()
        self._on_mode_changed()
        self.refresh()
        self._refresh_hint()

    def _mode(self) -> str:
        return str(self.mode_combo.currentData() or "once")

    def _set_field_visible(self, field: QWidget, visible: bool) -> None:
        field.setVisible(visible)
        label = self._form.labelForField(field)
        if label is not None:
            label.setVisible(visible)

    def _on_mode_changed(self, *_args: object) -> None:
        mode = self._mode()
        once = mode == "once"
        interval = mode == "interval"
        daily_like = mode in {"daily", "weekdays", "weekly"}
        weekly = mode == "weekly"
        custom = mode == "cron"
        show_cron = mode != "once"

        self._set_field_visible(self.run_at_edit, once)
        self.run_at_edit.setEnabled(once)
        self._set_field_visible(self.interval_wrap, interval)
        self.interval_wrap.setEnabled(interval)
        self._set_field_visible(self.time_edit, daily_like)
        self.time_edit.setEnabled(daily_like)
        self._set_field_visible(self.weekday_combo, weekly)
        self.weekday_combo.setEnabled(weekly)
        self._set_field_visible(self.cron_edit, show_cron)
        self.cron_edit.setReadOnly(not custom)
        self.cron_edit.setEnabled(show_cron)

        if mode not in {"once", "cron"}:
            self._apply_freq_to_cron()
        self._refresh_hint()

    def _on_freq_changed(self, *_args: object) -> None:
        if self._syncing_freq:
            return
        if self._mode() in {"interval", "daily", "weekdays", "weekly"}:
            self._apply_freq_to_cron()
            self._refresh_hint()

    def _on_cron_edited(self, *_args: object) -> None:
        if self._syncing_freq:
            return
        if self._mode() == "cron":
            self._refresh_hint()

    def _build_cron_from_ui(self) -> str:
        mode = self._mode()
        if mode == "interval":
            n = int(self.interval_spin.value())
            unit = self.interval_unit.currentData()
            if unit == "hour":
                return f"0 */{n} * * *"
            return f"*/{n} * * * *"
        if mode in {"daily", "weekdays", "weekly"}:
            t = self.time_edit.time()
            minute, hour = t.minute(), t.hour()
            if mode == "daily":
                return f"{minute} {hour} * * *"
            if mode == "weekdays":
                return f"{minute} {hour} * * 1-5"
            dow = int(self.weekday_combo.currentData())
            return f"{minute} {hour} * * {dow}"
        return self.cron_edit.text().strip()

    def _apply_freq_to_cron(self) -> None:
        expr = self._build_cron_from_ui()
        self._syncing_freq = True
        try:
            self.cron_edit.setText(expr)
        finally:
            self._syncing_freq = False

    def _apply_cron_to_freq_ui(self, expr: str) -> None:
        freq, params = detect_freq_from_cron(expr)
        self._syncing_freq = True
        try:
            if freq == "interval":
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("interval"))
                self.interval_spin.setValue(int(params.get("every") or 5))
                uidx = self.interval_unit.findData(params.get("unit") or "minute")
                self.interval_unit.setCurrentIndex(uidx if uidx >= 0 else 0)
            elif freq == "daily":
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("daily"))
                self.time_edit.setTime(
                    QTime(int(params.get("hour") or 17), int(params.get("minute") or 30))
                )
            elif freq == "weekdays":
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("weekdays"))
                self.time_edit.setTime(
                    QTime(int(params.get("hour") or 17), int(params.get("minute") or 30))
                )
            elif freq == "weekly":
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("weekly"))
                self.time_edit.setTime(
                    QTime(int(params.get("hour") or 17), int(params.get("minute") or 30))
                )
                didx = self.weekday_combo.findData(int(params.get("dow") or 1))
                self.weekday_combo.setCurrentIndex(didx if didx >= 0 else 1)
            else:
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("cron"))
            self.cron_edit.setText(expr)
        finally:
            self._syncing_freq = False
        self._on_mode_changed()

    def _reload_hosts(self) -> None:
        current = self.host_combo.currentData()
        self.host_combo.clear()
        self.host_combo.addItem("本机（未指定库存主机）", "")
        for h in self.host_svc.list_hosts():
            self.host_combo.addItem(f"{h.name} ({h.protocol.value})", h.id)
        if current:
            idx = self.host_combo.findData(current)
            if idx >= 0:
                self.host_combo.setCurrentIndex(idx)

    def _browse(self) -> None:
        start = playbooks_dir()
        if not any(start.rglob("*.yaml")) and not any(start.rglob("*.yml")):
            start = templates_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要定时执行的流程 YAML",
            str(start),
            "YAML (*.yaml *.yml)",
        )
        if path:
            self.path_edit.setText(path)

    def _refresh_hint(self) -> None:
        if self._mode() == "once":
            dt = _local_from_qdt(self.run_at_edit.dateTime())
            self.time_hint.setText(
                f"将在 {dt.strftime('%Y-%m-%d %H:%M')}（本地）执行一次，完成后自动停用。"
            )
            return
        expr = self.cron_edit.text().strip()
        if not expr:
            self.time_hint.setText("请选择频率或填写 Cron。")
            return
        try:
            croniter(expr, datetime.now().astimezone())
            base = datetime.now().astimezone()
            itr = croniter(expr, base)
            times: list[str] = []
            for _ in range(3):
                nxt = itr.get_next(datetime)
                if nxt.tzinfo is None:
                    nxt = nxt.replace(tzinfo=base.tzinfo)
                times.append(nxt.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
            label = humanize_cron(expr)
            self.time_hint.setText(
                f"{label}　·　Cron：{expr}\n接下来触发：" + " → ".join(times)
            )
        except (ValueError, KeyError, TypeError):
            self.time_hint.setText("Cron 表达式无效，请检查频率设置或自定义表达式。")

    def _clear_form(self) -> None:
        self._editing_id = None
        self.name_edit.clear()
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("once"))
        self.run_at_edit.setDateTime(_qdt_from_local(default_once_at()))
        self.interval_spin.setValue(5)
        self.interval_unit.setCurrentIndex(self.interval_unit.findData("minute"))
        self.time_edit.setTime(QTime(17, 30))
        self.weekday_combo.setCurrentIndex(self.weekday_combo.findData(1))
        self.cron_edit.setText(self.DEFAULT_CRON)
        self.path_edit.clear()
        self.host_combo.setCurrentIndex(0)
        self.enabled_check.setChecked(True)
        self.edit_hint.setText("当前：新建调度")
        self.table.clearSelection()
        self._on_mode_changed()

    def _on_select(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        sid = self.table.item(r, 0).text()
        self._editing_id = sid
        self.name_edit.setText(self.table.item(r, 1).text())
        mode = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole) or "cron"
        when = self.table.item(r, 3).data(Qt.ItemDataRole.UserRole) or ""
        if mode == "once" and when:
            self.mode_combo.setCurrentIndex(self.mode_combo.findData("once"))
            try:
                dt = datetime.fromisoformat(str(when))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_local_tz())
                self.run_at_edit.setDateTime(_qdt_from_local(dt))
            except ValueError:
                self.run_at_edit.setDateTime(_qdt_from_local(default_once_at()))
            self._on_mode_changed()
        else:
            self._apply_cron_to_freq_ui(str(when) or self.DEFAULT_CRON)
        self.enabled_check.setChecked(self.table.item(r, 4).text() == "是")
        host_id = self.table.item(r, 5).data(Qt.ItemDataRole.UserRole) or ""
        hidx = self.host_combo.findData(host_id)
        self.host_combo.setCurrentIndex(hidx if hidx >= 0 else 0)
        self.path_edit.setText(self.table.item(r, 8).text())
        self.edit_hint.setText(f"当前：编辑 {sid[:8]}…")

    def _fmt_last_run(self, value: datetime | None) -> str:
        if not value:
            return "—"
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def _host_label(self, host_id: str | None) -> tuple[str, str]:
        if not host_id:
            return "本机", ""
        for h in self.host_svc.list_hosts():
            if h.id == host_id:
                return f"{h.name} ({h.protocol.value})", host_id
        return f"(已删除) {host_id[:8]}…", host_id

    def _schedule_when(self, row) -> tuple[str, str, str]:
        """返回 (展示文案, 存贮数据, 模式标签)。"""
        mode = (getattr(row, "mode", None) or "cron").lower()
        if mode == "once":
            if row.run_at:
                local = _local_from_db(row.run_at)
                return (
                    f"一次 · {local.strftime('%Y-%m-%d %H:%M')}",
                    local.isoformat(),
                    "仅一次",
                )
            return "一次 · —", "", "仅一次"
        cron = row.cron or ""
        return humanize_cron(cron), cron, "周期"

    def refresh(self) -> None:
        self._reload_hosts()
        rows = self.container.scheduler.list_schedules()
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            host_text, host_id = self._host_label(r.host_id)
            mode = (getattr(r, "mode", None) or "cron").lower()
            when_text, when_data, mode_label = self._schedule_when(r)
            vals = [
                r.id,
                r.name,
                mode_label,
                when_text,
                "是" if r.enabled else "否",
                host_text,
                self._fmt_last_run(r.last_run_at),
                r.last_status or "—",
                r.playbook_path,
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if c == 2:
                    item.setData(Qt.ItemDataRole.UserRole, mode)
                if c == 3:
                    item.setData(Qt.ItemDataRole.UserRole, when_data)
                if c == 5:
                    item.setData(Qt.ItemDataRole.UserRole, host_id)
                self.table.setItem(i, c, item)
        if self._editing_id:
            for i in range(self.table.rowCount()):
                if self.table.item(i, 0).text() == self._editing_id:
                    self.table.selectRow(i)
                    break

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip()
        mode = self._mode()
        if not name:
            QMessageBox.warning(self, "校验", "请填写名称。")
            return
        if not path:
            QMessageBox.warning(self, "校验", "请选择要定时执行的流程 YAML。")
            return
        if not Path(path).is_file():
            QMessageBox.warning(self, "校验", f"流程文件不存在：\n{path}")
            return

        cron = ""
        run_at: datetime | None = None
        save_mode = "once" if mode == "once" else "cron"
        if mode == "once":
            # 本地墙钟；入库由 SchedulerService 转为 UTC
            run_at = _local_from_qdt(self.run_at_edit.dateTime())
        else:
            if mode != "cron":
                self._apply_freq_to_cron()
            cron = self.cron_edit.text().strip()
            if not cron:
                QMessageBox.warning(self, "校验", "请设置频率或填写 Cron。")
                return
            try:
                croniter(cron, datetime.now().astimezone())
            except (ValueError, KeyError, TypeError) as exc:
                QMessageBox.warning(self, "校验", f"Cron 无效：{exc}")
                return

        host_id = self.host_combo.currentData() or None
        if host_id == "":
            host_id = None
        try:
            sid = self.container.scheduler.upsert(
                name=name,
                mode=save_mode,
                cron=cron,
                run_at=run_at,
                playbook_path=path,
                host_id=host_id,
                enabled=self.enabled_check.isChecked(),
                schedule_id=self._editing_id,
            )
            self._editing_id = sid
            self.edit_hint.setText(f"当前：编辑 {sid[:8]}…")
            QMessageBox.information(self, "成功", "调度已保存。")
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _tick(self) -> None:
        fired = self.container.scheduler.tick_once()
        if fired:
            QMessageBox.information(
                self, "扫描完成", f"本次触发 {len(fired)} 个任务，可到「执行记录」查看。"
            )
        else:
            QMessageBox.information(self, "扫描完成", "本次没有到期任务。")
        self.refresh()

    def _toggle_enabled(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选中一条调度。")
            return
        sid = self.table.item(rows[0].row(), 0).text()
        enabled_now = self.table.item(rows[0].row(), 4).text() == "是"
        self.container.scheduler.set_enabled(sid, not enabled_now)
        self.refresh()

    def _delete(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选中一条调度。")
            return
        sid = self.table.item(rows[0].row(), 0).text()
        name = self.table.item(rows[0].row(), 1).text()
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除调度「{name}」？",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.container.scheduler.delete(sid)
        self._clear_form()
        self.refresh()
