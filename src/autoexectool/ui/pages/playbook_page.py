from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.orchestrator.loader import STEP_META
from autoexectool.runtime_paths import playbooks_dir, templates_dir
from autoexectool.ui.widgets.flow_canvas import FlowCanvas


class PlaybookPage(QWidget):
    """可视化流程画布 + 节点属性 + YAML 三栏编辑。"""

    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.current_path: Path | None = None
        self._syncing = False
        self._loading_props = False
        self._dirty_props = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("流程编排")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        tip = QLabel(
            "中间为实时渲染的流程画布：点选节点可在右侧编辑属性（含计划执行时间 schedule）。"
            "改完点「应用节点」写回 YAML；也可直接改底部 YAML，画布会同步刷新。"
            "节点级等到点 ≠ 任务调度页的流程 Cron。"
        )
        tip.setObjectName("MutedLabel")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        meta_row = QHBoxLayout()
        self.name_edit = QLineEdit("my-playbook")
        self.name_edit.setPlaceholderText("流程 name")
        self.name_edit.editingFinished.connect(self._apply_playbook_name)
        self.path_label = QLabel("未打开文件")
        self.path_label.setObjectName("MutedLabel")
        meta_row.addWidget(QLabel("流程名"))
        meta_row.addWidget(self.name_edit, 1)
        meta_row.addWidget(self.path_label, 2)
        layout.addLayout(meta_row)

        toolbar = QHBoxLayout()
        load_btn = QPushButton("打开…")
        load_btn.clicked.connect(self._load)
        save_btn = QPushButton("保存 YAML")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save)
        validate_btn = QPushButton("校验")
        validate_btn.clicked.connect(self._validate)
        add_stage_btn = QPushButton("添加阶段")
        add_stage_btn.clicked.connect(self._add_stage)
        add_step_btn = QPushButton("添加步骤")
        add_step_btn.clicked.connect(lambda: self._add_step(None))
        up_btn = QPushButton("上移")
        up_btn.clicked.connect(lambda: self._move_step(-1))
        down_btn = QPushButton("下移")
        down_btn.clicked.connect(lambda: self._move_step(1))
        del_btn = QPushButton("删除节点")
        del_btn.clicked.connect(self._delete_step)
        for b in (
            load_btn,
            save_btn,
            validate_btn,
            add_stage_btn,
            add_step_btn,
            up_btn,
            down_btn,
            del_btn,
        ):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        main_split = QSplitter(Qt.Orientation.Horizontal)

        center_split = QSplitter(Qt.Orientation.Vertical)
        self.canvas = FlowCanvas()
        self.canvas.selection_changed.connect(self._on_canvas_selection)
        self.canvas.add_step_requested.connect(self._add_step)
        self.canvas.add_stage_requested.connect(self._add_stage)
        center_split.addWidget(self.canvas)

        yaml_box = QWidget()
        yaml_layout = QVBoxLayout(yaml_box)
        yaml_layout.setContentsMargins(0, 0, 0, 0)
        yaml_layout.addWidget(QLabel("YAML（与画布双向同步）"))
        self.yaml_edit = QPlainTextEdit()
        self.yaml_edit.setPlainText(
            "name: my-playbook\nversion: 1\nstages:\n  - name: main\n    steps: []\n"
        )
        self.yaml_edit.textChanged.connect(self._on_yaml_changed)
        yaml_layout.addWidget(self.yaml_edit, 1)
        center_split.addWidget(yaml_box)
        center_split.setStretchFactor(0, 3)
        center_split.setStretchFactor(1, 2)
        center_split.setSizes([420, 220])
        main_split.addWidget(center_split)

        props_wrap = QWidget()
        props_wrap.setMinimumWidth(300)
        props_wrap.setMaximumWidth(380)
        props_outer = QVBoxLayout(props_wrap)
        props_outer.setContentsMargins(0, 0, 0, 0)
        props_title = QLabel("节点属性")
        props_title.setObjectName("TitleLabel")
        props_outer.addWidget(props_title)
        self.props_hint = QLabel("在画布中点选一个步骤进行编辑")
        self.props_hint.setObjectName("MutedLabel")
        self.props_hint.setWordWrap(True)
        props_outer.addWidget(self.props_hint)

        props_scroll = QScrollArea()
        props_scroll.setWidgetResizable(True)
        props_scroll.setFrameShape(QFrame.Shape.NoFrame)
        props_inner = QWidget()
        form = QFormLayout(props_inner)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.stage_name_edit = QLineEdit()
        self.stage_name_edit.setPlaceholderText("所属阶段名")
        self.step_id = QLineEdit()
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("动作 action", "action")
        self.kind_combo.addItem("引用流程 use_playbook", "playbook")
        self.kind_combo.addItem("指令组 use_group", "group")
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)

        self.action_combo = QComboBox()
        for row in container.actions.catalog(include_aliases=False):
            self.action_combo.addItem(row["label"], row["code"])
        self.use_playbook = QLineEdit()
        self.use_playbook.setPlaceholderText("子流程 YAML 路径")
        self.use_group = QLineEdit()
        self.use_group.setPlaceholderText("指令组名")

        self.host_ref = QLineEdit()
        self.host_ref.setPlaceholderText("空=会话默认；local / 主机名 / id")
        self.parallel_group = QLineEdit()
        self.parallel_group.setPlaceholderText("同名则并行")

        self.sched_enable = QCheckBox("启用计划执行时间（轮到本步后再等到点）")
        self.sched_at = QLineEdit()
        self.sched_at.setPlaceholderText("22:30 或 2026-11-23T22:30:00+08:00")
        self.sched_tz = QLineEdit("Asia/Shanghai")
        self.sched_if_past = QComboBox()
        self.sched_if_past.addItem("已过点则立即执行", "run_immediately")
        self.sched_if_past.addItem("已过点则失败", "fail")
        self.sched_if_past.addItem("已过点则跳过", "skip")
        self.sched_max_wait = QSpinBox()
        self.sched_max_wait.setRange(0, 86400 * 7)
        self.sched_max_wait.setSpecialValueText("不限制")
        self.sched_max_wait.setValue(0)

        self.success_exit = QSpinBox()
        self.success_exit.setRange(-1, 255)
        self.success_exit.setValue(-1)
        self.success_exit.setSpecialValueText("默认")
        self.timeout_sec = QSpinBox()
        self.timeout_sec.setRange(0, 86400)
        self.timeout_sec.setSpecialValueText("默认")
        self.timeout_sec.setValue(0)
        self.retries = QSpinBox()
        self.retries.setRange(0, 20)

        self.params_edit = QPlainTextEdit()
        self.params_edit.setPlaceholderText(
            "动作参数（YAML 字典），例如：\ncommand: echo hi\nlocal: ./dist\nremote: /tmp/x"
        )
        self.params_edit.setMinimumHeight(120)

        form.addRow("阶段名", self.stage_name_edit)
        form.addRow("步骤 ID", self.step_id)
        form.addRow("类型", self.kind_combo)
        form.addRow("动作", self.action_combo)
        form.addRow("引用流程", self.use_playbook)
        form.addRow("指令组", self.use_group)
        form.addRow("目标主机", self.host_ref)
        form.addRow("并行组", self.parallel_group)
        form.addRow("", self.sched_enable)
        form.addRow("execute_at", self.sched_at)
        form.addRow("时区", self.sched_tz)
        form.addRow("过期策略", self.sched_if_past)
        form.addRow("最长等待秒", self.sched_max_wait)
        form.addRow("成功退出码", self.success_exit)
        form.addRow("超时秒", self.timeout_sec)
        form.addRow("重试次数", self.retries)
        form.addRow("参数 YAML", self.params_edit)
        props_scroll.setWidget(props_inner)
        props_outer.addWidget(props_scroll, 1)

        apply_btn = QPushButton("应用节点")
        apply_btn.setObjectName("PrimaryButton")
        apply_btn.setToolTip("将右侧属性写回当前选中节点，并刷新画布 / YAML")
        apply_btn.clicked.connect(self._apply_props)
        props_outer.addWidget(apply_btn)

        main_split.addWidget(props_wrap)
        main_split.setStretchFactor(0, 5)
        main_split.setStretchFactor(1, 2)
        main_split.setSizes([760, 340])
        layout.addWidget(main_split, 1)

        self._props_widgets = [
            self.stage_name_edit,
            self.step_id,
            self.kind_combo,
            self.action_combo,
            self.use_playbook,
            self.use_group,
            self.host_ref,
            self.parallel_group,
            self.sched_enable,
            self.sched_at,
            self.sched_tz,
            self.sched_if_past,
            self.sched_max_wait,
            self.success_exit,
            self.timeout_sec,
            self.retries,
            self.params_edit,
        ]
        for w in self._props_widgets:
            self._wire_dirty(w)
        self._set_props_enabled(False)
        self._on_kind_changed()
        self._refresh_canvas()

    def _wire_dirty(self, widget: QWidget) -> None:
        if isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._mark_dirty)
        elif isinstance(widget, QPlainTextEdit):
            widget.textChanged.connect(self._mark_dirty)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._mark_dirty)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self._mark_dirty)
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(self._mark_dirty)

    def _mark_dirty(self, *_args: Any) -> None:
        if self._loading_props:
            return
        self._dirty_props = True

    def _set_props_enabled(self, enabled: bool) -> None:
        for w in self._props_widgets:
            w.setEnabled(enabled)

    def _parse(self) -> dict[str, Any]:
        data = yaml.safe_load(self.yaml_edit.toPlainText()) or {}
        if not isinstance(data, dict):
            raise ValueError("YAML 根须为字典")
        return data

    def _ensure_stages(self, data: dict[str, Any]) -> list:
        if "stages" not in data or not data["stages"]:
            data["stages"] = [{"name": "main", "steps": []}]
        for st in data["stages"]:
            if isinstance(st, dict):
                st.setdefault("steps", [])
        return data["stages"]

    def _dump(self, data: dict[str, Any], *, keep_selection: bool = True) -> None:
        sel = self.canvas.selected if keep_selection else None
        self._syncing = True
        try:
            self.yaml_edit.setPlainText(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            )
        finally:
            self._syncing = False
        self._refresh_canvas(select=sel)

    def _refresh_canvas(self, select: tuple[int, int] | None = None) -> None:
        try:
            data = self._parse()
            if data.get("name"):
                self.name_edit.blockSignals(True)
                self.name_edit.setText(str(data["name"]))
                self.name_edit.blockSignals(False)
        except Exception:  # noqa: BLE001
            data = {"stages": []}
        if select is not None:
            self.canvas._selected = select
        self.canvas.render(data)

    def _on_yaml_changed(self) -> None:
        if self._syncing:
            return
        self._refresh_canvas(select=self.canvas.selected)

    def _on_kind_changed(self, *_args: Any) -> None:
        kind = self.kind_combo.currentData()
        self.action_combo.setEnabled(kind == "action")
        self.use_playbook.setEnabled(kind == "playbook")
        self.use_group.setEnabled(kind == "group")

    def _on_canvas_selection(self, stage_idx: int, step_idx: int) -> None:
        if stage_idx < 0:
            self._set_props_enabled(False)
            self.props_hint.setText("在画布中点选一个步骤进行编辑")
            self._dirty_props = False
            return
        if self._dirty_props:
            reply = QMessageBox.question(
                self,
                "未应用的修改",
                "当前节点有未应用的修改，是否先应用？\n选「否」将丢弃修改并加载新节点。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes and not self._apply_props(silent=True):
                return
        self._load_props(stage_idx, step_idx)

    def _load_props(self, stage_idx: int, step_idx: int) -> None:
        try:
            data = self._parse()
            stages = self._ensure_stages(data)
            stage = stages[stage_idx]
            step = stage["steps"][step_idx]
        except Exception:  # noqa: BLE001
            self._set_props_enabled(False)
            return

        self._loading_props = True
        try:
            self._set_props_enabled(True)
            self.props_hint.setText(f"正在编辑：阶段 {stage_idx + 1} / 步骤 {step_idx + 1}")
            self.stage_name_edit.setText(str(stage.get("name") or ""))
            self.step_id.setText(str(step.get("id") or ""))

            if step.get("use_playbook"):
                self.kind_combo.setCurrentIndex(self.kind_combo.findData("playbook"))
                self.use_playbook.setText(str(step.get("use_playbook") or ""))
            elif step.get("use_group"):
                self.kind_combo.setCurrentIndex(self.kind_combo.findData("group"))
                self.use_group.setText(str(step.get("use_group") or ""))
            else:
                self.kind_combo.setCurrentIndex(self.kind_combo.findData("action"))
                action = str(step.get("action") or "")
                idx = self.action_combo.findData(action)
                if idx < 0:
                    idx = self.action_combo.findText(action, Qt.MatchFlag.MatchContains)
                if idx >= 0:
                    self.action_combo.setCurrentIndex(idx)

            self.host_ref.setText(str(step.get("host") or ""))
            self.parallel_group.setText(str(step.get("parallel_group") or ""))

            sched = step.get("schedule") if isinstance(step.get("schedule"), dict) else None
            self.sched_enable.setChecked(bool(sched and sched.get("execute_at")))
            self.sched_at.setText(str((sched or {}).get("execute_at") or ""))
            self.sched_tz.setText(str((sched or {}).get("timezone") or "Asia/Shanghai"))
            if_past = str((sched or {}).get("if_past") or "run_immediately")
            ip = self.sched_if_past.findData(if_past)
            self.sched_if_past.setCurrentIndex(ip if ip >= 0 else 0)
            mw = (sched or {}).get("max_wait_sec")
            self.sched_max_wait.setValue(int(mw) if mw else 0)

            sw = step.get("success_when") if isinstance(step.get("success_when"), dict) else {}
            if "exit_code" in (sw or {}):
                self.success_exit.setValue(int(sw["exit_code"]))
            else:
                self.success_exit.setValue(-1)

            self.timeout_sec.setValue(int(step["timeout_sec"]) if step.get("timeout_sec") else 0)
            self.retries.setValue(int(step.get("retries") or 0))

            params = {k: v for k, v in step.items() if k not in STEP_META}
            if params:
                self.params_edit.setPlainText(
                    yaml.safe_dump(params, allow_unicode=True, sort_keys=False).rstrip()
                )
            else:
                self.params_edit.clear()
            self._on_kind_changed()
        finally:
            self._loading_props = False
            self._dirty_props = False

    def _apply_props(self, *, silent: bool = False) -> bool:
        sel = self.canvas.selected
        if not sel:
            if not silent:
                QMessageBox.information(self, "提示", "请先在画布中选中一个步骤。")
            return False
        stage_idx, step_idx = sel
        try:
            data = self._parse()
            stages = self._ensure_stages(data)
            stage = stages[stage_idx]
            steps = stage.setdefault("steps", [])
            if step_idx >= len(steps):
                raise ValueError("选中步骤已不存在，请重新点选")

            stage_name = self.stage_name_edit.text().strip()
            if stage_name:
                stage["name"] = stage_name

            kind = self.kind_combo.currentData()
            step: dict[str, Any] = {"id": self.step_id.text().strip() or f"step{step_idx + 1}"}

            params_text = self.params_edit.toPlainText().strip()
            params: dict[str, Any] = {}
            if params_text:
                loaded = yaml.safe_load(params_text)
                if loaded is None:
                    params = {}
                elif not isinstance(loaded, dict):
                    raise ValueError("参数 YAML 须为字典（键值对）")
                else:
                    params = loaded

            if kind == "playbook":
                ref = self.use_playbook.text().strip()
                if not ref:
                    raise ValueError("请填写引用流程路径")
                step["use_playbook"] = ref
            elif kind == "group":
                g = self.use_group.text().strip()
                if not g:
                    raise ValueError("请填写指令组名")
                step["use_group"] = g
            else:
                action = self.action_combo.currentData() or self.action_combo.currentText()
                step["action"] = str(action)

            step.update(params)

            href = self.host_ref.text().strip()
            if href:
                step["host"] = href
            pg = self.parallel_group.text().strip()
            if pg:
                step["parallel_group"] = pg

            if self.sched_enable.isChecked():
                at = self.sched_at.text().strip()
                if not at:
                    raise ValueError("启用计划执行时间时请填写 execute_at")
                schedule: dict[str, Any] = {
                    "execute_at": at,
                    "timezone": self.sched_tz.text().strip() or "Asia/Shanghai",
                    "if_past": self.sched_if_past.currentData(),
                }
                if self.sched_max_wait.value() > 0:
                    schedule["max_wait_sec"] = int(self.sched_max_wait.value())
                step["schedule"] = schedule

            if self.success_exit.value() >= 0:
                step["success_when"] = {"exit_code": int(self.success_exit.value())}
            if self.timeout_sec.value() > 0:
                step["timeout_sec"] = int(self.timeout_sec.value())
            if self.retries.value() > 0:
                step["retries"] = int(self.retries.value())

            steps[step_idx] = step
            data["name"] = self.name_edit.text().strip() or data.get("name") or "my-playbook"
            self._dirty_props = False
            self._dump(data, keep_selection=True)
            self.canvas.select(stage_idx, step_idx)
            if not silent:
                self.props_hint.setText(f"已应用：阶段 {stage_idx + 1} / 步骤 {step_idx + 1}")
            return True
        except Exception as exc:  # noqa: BLE001
            if not silent:
                QMessageBox.critical(self, "应用失败", str(exc))
            return False

    def _apply_playbook_name(self) -> None:
        try:
            data = self._parse()
            data["name"] = self.name_edit.text().strip() or data.get("name") or "my-playbook"
            self._dump(data)
        except Exception:  # noqa: BLE001
            pass

    def _add_stage(self) -> None:
        try:
            data = self._parse()
            stages = self._ensure_stages(data)
            stages.append({"name": f"stage{len(stages) + 1}", "steps": []})
            self._dump(data, keep_selection=False)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _add_step(self, stage_idx: int | None) -> None:
        try:
            data = self._parse()
            stages = self._ensure_stages(data)
            if stage_idx is None:
                sel = self.canvas.selected
                stage_idx = sel[0] if sel else len(stages) - 1
            if stage_idx < 0 or stage_idx >= len(stages):
                stage_idx = len(stages) - 1
            steps = stages[stage_idx].setdefault("steps", [])
            n = len(steps) + 1
            steps.append({"id": f"step{n}", "action": "cmd.exec", "command": "echo ok"})
            self._dump(data, keep_selection=False)
            self.canvas.select(stage_idx, len(steps) - 1)
            self._load_props(stage_idx, len(steps) - 1)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _move_step(self, delta: int) -> None:
        sel = self.canvas.selected
        if not sel:
            return
        stage_idx, step_idx = sel
        try:
            data = self._parse()
            steps = self._ensure_stages(data)[stage_idx].setdefault("steps", [])
            new_idx = step_idx + delta
            if new_idx < 0 or new_idx >= len(steps):
                return
            steps[step_idx], steps[new_idx] = steps[new_idx], steps[step_idx]
            self._dirty_props = False
            self._dump(data, keep_selection=False)
            self.canvas.select(stage_idx, new_idx)
            self._load_props(stage_idx, new_idx)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _delete_step(self) -> None:
        sel = self.canvas.selected
        if not sel:
            QMessageBox.information(self, "提示", "请先选中要删除的步骤。")
            return
        stage_idx, step_idx = sel
        try:
            data = self._parse()
            stages = self._ensure_stages(data)
            steps = stages[stage_idx].setdefault("steps", [])
            if step_idx < len(steps):
                steps.pop(step_idx)
            # 空阶段也保留，便于继续加步
            self._dirty_props = False
            self._dump(data, keep_selection=False)
            self.canvas.clear_selection()
            self._set_props_enabled(False)
            self.props_hint.setText("在画布中点选一个步骤进行编辑")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "失败", str(exc))

    def _load(self) -> None:
        start = playbooks_dir()
        if not any(start.rglob("*.yaml")) and not any(start.rglob("*.yml")):
            start = templates_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开流程",
            str(start),
            "YAML (*.yaml *.yml)",
        )
        if not path:
            return
        self.current_path = Path(path)
        self._syncing = True
        try:
            self.yaml_edit.setPlainText(self.current_path.read_text(encoding="utf-8"))
        finally:
            self._syncing = False
        self.path_label.setText(str(self.current_path))
        self._dirty_props = False
        self.canvas.clear_selection()
        self._set_props_enabled(False)
        self._refresh_canvas()

    def _save(self) -> None:
        default_dir = playbooks_dir()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存流程",
            str(
                self.current_path
                or (default_dir / f"{self.name_edit.text() or 'playbook'}.yaml")
            ),
            "YAML (*.yaml)",
        )
        if not path:
            return
        if self._dirty_props:
            self._apply_props(silent=True)
        p = Path(path)
        p.write_text(self.yaml_edit.toPlainText(), encoding="utf-8")
        self.current_path = p
        self.path_label.setText(str(p))
        QMessageBox.information(self, "成功", f"已保存：{p}")

    def _validate(self) -> None:
        from autoexectool.orchestrator.loader import parse_playbook_dict

        if self._dirty_props:
            self._apply_props(silent=True)
        try:
            data = self._parse()
            spec = parse_playbook_dict(data)
            prepared = self.container.orchestrator._prepare(
                spec, playbook_path=str(self.current_path or "")
            )
            actions = [s.action for st in prepared.stages for s in st.steps]
            for a in actions:
                self.container.actions.get(a)
            QMessageBox.information(
                self,
                "校验通过",
                f"流程 {spec.name}，阶段 {len(prepared.stages)}，"
                f"展开后 {len(actions)} 步。\n动作：{', '.join(actions) or '无'}",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "校验失败", str(exc))
