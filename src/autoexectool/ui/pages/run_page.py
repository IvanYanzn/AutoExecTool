from __future__ import annotations

import json
import platform
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from autoexectool.app.container import AppContainer
from autoexectool.application.host_service import HostService
from autoexectool.domain.enums import ProtocolType
from autoexectool.domain.models import Host, PlaybookSpec
from autoexectool.orchestrator.loader import load_playbook_yaml
from autoexectool.orchestrator.serialize import playbook_to_dict
from autoexectool.orchestrator.timeline import TimelineReader
from autoexectool.runtime_paths import playbooks_dir, templates_dir
from autoexectool.storage.repositories import VariableSetRepository
from autoexectool.ui.notify import popup
from autoexectool.ui.widgets.log_console import LogConsole


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class _ExecuteWorker(QObject):
    """后台只跑编排；Signal 仅用于生命周期，不传日志正文。"""

    session_ready = Signal(str)
    finished = Signal(bool, str)

    def __init__(
        self,
        *,
        orchestrator: Any,
        spec: PlaybookSpec,
        targets: list[tuple[Host, Any]],
        variables: dict[str, Any],
        playbook_path: str,
        playbook_json: str,
        max_parallel: int,
    ) -> None:
        super().__init__()
        self._orchestrator = orchestrator
        self._spec = spec
        self._targets = targets
        self._variables = variables
        self._playbook_path = playbook_path
        self._playbook_json = playbook_json
        self._max_parallel = max_parallel

    def run(self) -> None:
        try:
            session_ids: list[str] = []

            def on_session(session_id: str) -> None:
                self.session_ready.emit(session_id)

            if len(self._targets) == 1:
                host, cred = self._targets[0]
                sid = self._orchestrator.start(
                    self._spec,
                    host,
                    credential=cred,
                    variables=self._variables,
                    dry_run=False,
                    on_session=on_session,
                    playbook_path=self._playbook_path,
                    playbook_json=self._playbook_json,
                )
                session_ids.append(sid)
            else:

                def _one(item: tuple[Host, Any]) -> str:
                    h, c = item
                    return self._orchestrator.start(
                        self._spec,
                        h,
                        credential=c,
                        variables=self._variables,
                        dry_run=False,
                        on_session=on_session,
                        playbook_path=self._playbook_path,
                        playbook_json=self._playbook_json,
                    )

                with ThreadPoolExecutor(
                    max_workers=max(1, self._max_parallel)
                ) as pool:
                    futs = [pool.submit(_one, item) for item in self._targets]
                    for fut in as_completed(futs):
                        session_ids.append(fut.result())

            finals = [
                self._orchestrator.get_status(sid) for sid in session_ids
            ]
            if any(str(r.status) == "Cancelled" for r in finals):
                self.finished.emit(False, "任务已被取消")
            elif any(str(r.status) == "Failed" for r in finals):
                summary = next(
                    (r.summary for r in finals if str(r.status) == "Failed"),
                    "执行失败",
                )
                self.finished.emit(False, summary or "执行失败")
            else:
                self.finished.emit(True, ",".join(session_ids))
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))


class RunSessionPanel(QWidget):
    """单个执行标签页：独立流程、目标、日志与后台线程。"""

    title_changed = Signal()
    request_close = Signal()

    def __init__(self, container: AppContainer, *, with_default_sample: bool = True) -> None:
        super().__init__()
        self.container = container
        self.svc = HostService(container)
        self.playbook_path: Path | None = None
        self._thread: QThread | None = None
        self._worker: _ExecuteWorker | None = None
        self._busy = False
        self._tail: TimelineReader | None = None
        self._tailed_sessions: set[str] = set()
        self._active_session_ids: list[str] = []
        self._tab_index = 0
        self._task_t0: float | None = None
        self._step_t0: float | None = None
        self._step_name: str = ""
        self._step_running: bool = False
        self._task_elapsed_final: str = ""
        self._step_elapsed_final: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        form = QFormLayout()
        self.path_label = QLabel("未选择流程文件")
        self.path_label.setObjectName("MutedLabel")
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_label, 1)
        btn_pick = QPushButton("选择 YAML…")
        btn_pick.clicked.connect(self._pick)
        path_row.addWidget(btn_pick)
        form.addRow("流程", path_row)

        self.target_mode = QComboBox()
        self.target_mode.addItems(["本机", "指定主机", "主机组"])
        self.target_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("目标类型", self.target_mode)

        self.host_combo = QComboBox()
        self.group_combo = QComboBox()
        self.varset_combo = QComboBox()
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 50)
        self.parallel_spin.setValue(5)
        form.addRow("主机", self.host_combo)
        form.addRow("主机组", self.group_combo)
        form.addRow("变量集", self.varset_combo)
        form.addRow("组内并发", self.parallel_spin)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新目标")
        self.btn_refresh.clicked.connect(self.refresh_targets)
        self.btn_dry = QPushButton("Dry-run")
        self.btn_dry.clicked.connect(lambda: self._run(dry_run=True))
        self.btn_run = QPushButton("执行")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.clicked.connect(lambda: self._run(dry_run=False))
        self.btn_cancel = QPushButton("中止")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_run)
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_dry)
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        self.elapsed_task_label = QLabel("任务 —")
        self.elapsed_task_label.setObjectName("MutedLabel")
        self.elapsed_task_label.setToolTip("本标签当前任务已执行时长")
        self.elapsed_step_label = QLabel("节点 —")
        self.elapsed_step_label.setObjectName("MutedLabel")
        self.elapsed_step_label.setToolTip("当前节点已执行时长（进入「执行中」后开始计时）")
        row.addWidget(self.elapsed_task_label)
        row.addWidget(self.elapsed_step_label)
        layout.addLayout(row)

        self.output = LogConsole()
        layout.addWidget(self.output, 1)

        self._poll = QTimer(self)
        self._poll.setInterval(300)
        self._poll.timeout.connect(self._poll_timeline)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._refresh_elapsed)

        if with_default_sample:
            tpl = templates_dir()
            sample = tpl / "demos" / "local_smoke.yaml"
            if not sample.exists():
                sample = tpl / "demos" / "local_smoke_windows.yaml"
            if not sample.exists():
                # 兼容旧路径或其它分组
                found = list(tpl.rglob("local_smoke_windows.yaml")) or list(
                    tpl.rglob("local_smoke.yaml")
                )
                sample = found[0] if found else sample
            if sample.exists():
                self.playbook_path = sample
                self.path_label.setText(str(sample))

        self.refresh_targets()
        self._on_mode_changed()

    @property
    def is_busy(self) -> bool:
        return self._busy

    def tab_title(self) -> str:
        if self.playbook_path:
            name = self.playbook_path.stem
        else:
            name = f"执行 {self._tab_index + 1}"
        if len(name) > 22:
            name = name[:20] + "…"
        return f"● {name}" if self._busy else name

    def set_tab_index(self, index: int) -> None:
        self._tab_index = index
        self.title_changed.emit()

    def refresh_targets(self) -> None:
        current_host = self.host_combo.currentData()
        current_group = self.group_combo.currentData()
        current_var = self.varset_combo.currentData()
        self.host_combo.clear()
        for h in self.svc.list_hosts():
            self.host_combo.addItem(f"{h.name} ({h.protocol.value})", h.id)
        self.group_combo.clear()
        for g in self.svc.list_host_groups():
            self.group_combo.addItem(f"{g.name} ({len(g.host_ids)} 台)", g.id)
        self.varset_combo.clear()
        self.varset_combo.addItem("（无）", "")
        with self.container.session_factory() as session:
            for row in VariableSetRepository(session).list():
                self.varset_combo.addItem(row.name, row.name)
        if current_host:
            idx = self.host_combo.findData(current_host)
            if idx >= 0:
                self.host_combo.setCurrentIndex(idx)
        if current_group:
            idx = self.group_combo.findData(current_group)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        if current_var:
            idx = self.varset_combo.findData(current_var)
            if idx >= 0:
                self.varset_combo.setCurrentIndex(idx)

    def _on_mode_changed(self) -> None:
        mode = self.target_mode.currentIndex()
        self.host_combo.setEnabled(mode == 1 and not self._busy)
        self.group_combo.setEnabled(mode == 2 and not self._busy)
        self.parallel_spin.setEnabled(mode == 2 and not self._busy)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.btn_refresh.setEnabled(not busy)
        self.btn_dry.setEnabled(not busy)
        self.btn_run.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.target_mode.setEnabled(not busy)
        self.varset_combo.setEnabled(not busy)
        self._on_mode_changed()
        self.btn_run.setText("执行中…" if busy else "执行")
        if busy:
            self._task_t0 = time.monotonic()
            self._step_t0 = None
            self._step_name = ""
            self._step_running = False
            self._task_elapsed_final = ""
            self._step_elapsed_final = ""
            self._refresh_elapsed()
            if not self._elapsed_timer.isActive():
                self._elapsed_timer.start()
        else:
            self._refresh_elapsed()
            self._elapsed_timer.stop()
        self.title_changed.emit()

    def _refresh_elapsed(self) -> None:
        if self._task_t0 is not None and self._busy:
            self.elapsed_task_label.setText(
                f"任务 {_format_elapsed(time.monotonic() - self._task_t0)}"
            )
        elif self._task_elapsed_final:
            self.elapsed_task_label.setText(f"任务 {self._task_elapsed_final}")
        elif not self._busy:
            self.elapsed_task_label.setText("任务 —")

        if self._step_running and self._step_t0 is not None and self._busy:
            name = self._step_name or "…"
            self.elapsed_step_label.setText(
                f"节点 {name} {_format_elapsed(time.monotonic() - self._step_t0)}"
            )
        elif self._step_elapsed_final:
            self.elapsed_step_label.setText(f"节点 {self._step_elapsed_final}")
        elif self._step_name and not self._step_running:
            self.elapsed_step_label.setText(f"节点 {self._step_name} —")
        elif not self._busy and not self._step_elapsed_final:
            self.elapsed_step_label.setText("节点 —")

    def _note_step_from_event(self, event: dict[str, Any]) -> None:
        cat = str(event.get("cat") or "")
        step = str(event.get("step") or "").strip()
        msg = str(event.get("message") or "")
        if not step:
            return
        if cat == "exec" or (cat == "node" and "执行中" in msg):
            self._step_name = step
            self._step_t0 = time.monotonic()
            self._step_running = True
            self._refresh_elapsed()
            return
        if cat == "node" and (
            msg.startswith("成功")
            or msg.startswith("失败")
            or "跳过" in msg
        ):
            if self._step_running and self._step_t0 is not None:
                elapsed = _format_elapsed(time.monotonic() - self._step_t0)
                self._step_elapsed_final = f"{step} {elapsed}"
            self._step_running = False
            self._refresh_elapsed()

    def _cancel_run(self) -> None:
        if not self._busy:
            return
        ids = list(self._active_session_ids) or list(self._tailed_sessions)
        if not ids:
            QMessageBox.warning(
                self, "提示", "尚未拿到会话 ID，请稍候再点中止，或直接关闭程序。"
            )
            return
        self._request_cancel(ids)
        popup(self, "已请求中止", "正在终止当前步骤，请稍候查看时间线。")

    def _request_cancel(self, ids: list[str] | None = None) -> None:
        targets = ids or list(self._active_session_ids) or list(self._tailed_sessions)
        for sid in targets:
            try:
                self.container.orchestrator.cancel(sid)
            except Exception as exc:  # noqa: BLE001
                self.output.append_line(f"中止请求失败：{sid} | {exc}", "fail")
        self.output.append_line("已请求中止（将结束当前命令并取消后续步骤）…", "warn")

    def request_cancel_and_stop(self, wait_ms: int = 5000) -> None:
        """关闭标签前：请求中止并尽量等后台线程退出。"""
        self._request_cancel()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(wait_ms)
        self._poll.stop()
        self._elapsed_timer.stop()
        self._busy = False
        self._worker = None
        self._thread = None

    def reset_for_reuse(self) -> None:
        """最后一个标签被关闭时清空，而不是删掉。"""
        self.request_cancel_and_stop(wait_ms=2000)
        self.output.clear_log()
        self.playbook_path = None
        self.path_label.setText("未选择流程文件")
        self._tail = None
        self._tailed_sessions.clear()
        self._active_session_ids.clear()
        self._task_t0 = None
        self._step_t0 = None
        self._step_name = ""
        self._step_running = False
        self._task_elapsed_final = ""
        self._step_elapsed_final = ""
        self._set_busy(False)
        self.elapsed_task_label.setText("任务 —")
        self.elapsed_step_label.setText("节点 —")

    def _pick(self) -> None:
        # 默认打开业务编排目录（data/config/playbooks）；若无 yaml 则退回内置 templates
        start = playbooks_dir()
        if not any(start.rglob("*.yaml")) and not any(start.rglob("*.yml")):
            start = templates_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择流程 YAML",
            str(start),
            "YAML (*.yaml *.yml)",
        )
        if path:
            self.playbook_path = Path(path)
            self.path_label.setText(path)
            self.title_changed.emit()

    def _ensure_local_host(self) -> Host:
        for h in self.svc.list_hosts():
            if h.protocol == ProtocolType.LOCAL:
                return h
        return self.svc.upsert_host(
            name="本机",
            address="127.0.0.1",
            protocol="local",
            os_type="windows" if platform.system() == "Windows" else "linux",
        )

    def _load_variables(self) -> dict:
        name = self.varset_combo.currentData() or ""
        if not name:
            return {}
        with self.container.session_factory() as session:
            return VariableSetRepository(session).get_vars(str(name))

    def _resolve_targets(self) -> list[tuple[Host, object | None]]:
        mode = self.target_mode.currentIndex()
        if mode == 0:
            return [(self._ensure_local_host(), None)]
        if mode == 1:
            host_id = self.host_combo.currentData()
            if not host_id:
                raise ValueError("请选择主机")
            return self.svc.resolve_hosts_with_credentials(host_id=str(host_id))
        group_id = self.group_combo.currentData()
        if not group_id:
            raise ValueError("请选择主机组")
        targets = self.svc.resolve_hosts_with_credentials(group_id=str(group_id))
        if not targets:
            raise ValueError("主机组内无主机")
        return targets

    def _timeline_path(self, session_id: str) -> Path:
        return self.container.paths.logs_exec / session_id / "timeline.jsonl"

    def _on_session_ready(self, session_id: str) -> None:
        if session_id not in self._active_session_ids:
            self._active_session_ids.append(session_id)
        if session_id in self._tailed_sessions:
            return
        self._tailed_sessions.add(session_id)
        path = self._timeline_path(session_id)
        if self._tail is None:
            self._tail = TimelineReader(path)
            self.output.append_line(f"会话已创建：{session_id}", "meta")
            self.output.append_line(f"时间线：{path}", "info")
            if not self._poll.isActive():
                self._poll.start()
            self._poll_timeline()
            popup(
                self,
                "任务已开始",
                f"会话：{session_id}\n日志按类别写入时间线，可切到其他标签或页面稍后再回来查看。",
            )
        else:
            self.output.append_line(f"附加会话：{session_id}", "meta")
            self._poll_timeline()
            self._tail = TimelineReader(path)
            self._poll_timeline()

    def _poll_timeline(self) -> None:
        if self._tail is None:
            return
        for event in self._tail.read_new():
            self._note_step_from_event(event)
            self.output.append_event(event)

    def _on_worker_finished(self, ok: bool, message: str) -> None:
        self._poll_timeline()
        self._poll.stop()
        cancelled = (not ok) and (
            "取消" in (message or "")
            or "CANCELLED" in (message or "").upper()
            or "中止" in (message or "")
        )
        # 定格最终耗时，再结束 busy
        if self._task_t0 is not None:
            self._task_elapsed_final = _format_elapsed(
                time.monotonic() - self._task_t0
            )
        if self._step_running and self._step_t0 is not None:
            self._step_elapsed_final = (
                f"{self._step_name or '…'} "
                f"{_format_elapsed(time.monotonic() - self._step_t0)}"
            )
            self._step_running = False
        kind = "ok" if ok else ("warn" if cancelled else "fail")
        if ok:
            popup(
                self,
                "任务已结束",
                f"执行成功。\n会话：{message or '（无）'}\n可在「执行记录」中回看完整时间线。",
            )
        elif cancelled:
            popup(self, "任务已中止", message or "用户取消", auto_close_ms=4000)
        else:
            popup(self, "任务失败", message, error=True, auto_close_ms=0)
        if message:
            self.output.append_line(f"会话 ID：{message}", "meta")
        self.output.append_line(
            "（上方时间线末尾含执行结果摘要：起止时间、耗时、步骤明细）",
            kind,
        )
        self._set_busy(False)
        self._tail = None
        self._tailed_sessions.clear()
        self._active_session_ids.clear()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None
            self._worker = None

    def _start_execute(
        self,
        *,
        spec: PlaybookSpec,
        targets: list[tuple[Host, object | None]],
        variables: dict,
    ) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.warning(self, "提示", "本标签已有任务在执行中。")
            return

        snapshot = playbook_to_dict(spec)
        playbook_json = json.dumps(snapshot, ensure_ascii=False)
        self.output.clear_log()
        self._tail = None
        self._tailed_sessions.clear()
        self._active_session_ids.clear()
        self.output.append_line("已提交后台执行；日志来自时间线文件（按类别渲染）", "meta")
        self.output.append_line(f"流程：{self.playbook_path}", "info")
        self.output.append_line("需要停止时请点「中止」", "info")

        self._thread = QThread(self)
        self._worker = _ExecuteWorker(
            orchestrator=self.container.orchestrator,
            spec=spec,
            targets=targets,
            variables=variables,
            playbook_path=str(self.playbook_path),
            playbook_json=playbook_json,
            max_parallel=int(self.parallel_spin.value()),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.session_ready.connect(self._on_session_ready)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._set_busy(True)
        self._thread.start()

    def _run(self, dry_run: bool) -> None:
        if self._busy:
            QMessageBox.warning(self, "提示", "本标签已有任务在执行中，请稍候。")
            return
        if not self.playbook_path:
            QMessageBox.warning(self, "提示", "请先选择流程 YAML。")
            return
        try:
            spec = load_playbook_yaml(self.playbook_path)
            variables = self._load_variables()
            targets = self._resolve_targets()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "执行失败", str(exc))
            return

        if dry_run:
            self.output.clear_log()
            self.output.append_line("Dry-run 预览（不会实际执行）", "dry")
            self.output.append_line(f"流程：{self.playbook_path}", "meta")
            self.output.append_blank()
            try:
                for host, _cred in targets:
                    self.output.append_line(f"═══ 目标：{host.name} ═══", "meta")
                    plan = self.container.orchestrator.dry_run(
                        spec,
                        host,
                        variables=variables,
                        playbook_path=str(self.playbook_path or ""),
                    )
                    for line in plan:
                        self.output.append_line(
                            line, LogConsole.kind_for_plan_line(line)
                        )
                    self.output.append_blank()
                self.output.append_line("Dry-run 结束", "ok")
            except Exception as exc:  # noqa: BLE001
                self.output.append_line(f"Dry-run 失败：{exc}", "fail")
                QMessageBox.critical(self, "执行失败", str(exc))
            return

        self._start_execute(spec=spec, targets=targets, variables=variables)


class RunPage(QWidget):
    """执行流程：多标签，各标签独立配置与并行执行。"""

    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self._tab_seq = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        head = QHBoxLayout()
        title = QLabel("执行流程")
        title.setObjectName("TitleLabel")
        head.addWidget(title)
        head.addStretch(1)
        self.btn_new_tab = QPushButton("新标签")
        self.btn_new_tab.setToolTip("再开一个执行页，可同时跑不同流程（日志互不干扰）")
        self.btn_new_tab.clicked.connect(lambda: self._add_tab(with_default_sample=False))
        head.addWidget(self.btn_new_tab)
        layout.addLayout(head)

        hint = QLabel(
            "每个标签可独立选择流程并执行。"
            "步骤若写了 host（库存主机名/id/local），将按步骤切换连接与凭证；"
            "未写则使用本页「目标类型」作为默认。"
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        layout.addWidget(self.tabs, 1)

        self._add_tab(with_default_sample=True)

    def _add_tab(self, *, with_default_sample: bool = False) -> None:
        panel = RunSessionPanel(
            self.container, with_default_sample=with_default_sample
        )
        self._tab_seq += 1
        panel.set_tab_index(self._tab_seq - 1)
        panel.title_changed.connect(lambda p=panel: self._sync_tab_title(p))
        idx = self.tabs.addTab(panel, panel.tab_title())
        self.tabs.setCurrentIndex(idx)
        self._sync_tab_title(panel)

    def _sync_tab_title(self, panel: RunSessionPanel) -> None:
        idx = self.tabs.indexOf(panel)
        if idx < 0:
            return
        self.tabs.setTabText(idx, panel.tab_title())
        tip = str(panel.playbook_path) if panel.playbook_path else "未选择流程"
        if panel.is_busy:
            tip = f"[执行中] {tip}"
        self.tabs.setTabToolTip(idx, tip)

    def _close_tab(self, index: int) -> None:
        panel = self.tabs.widget(index)
        if not isinstance(panel, RunSessionPanel):
            return
        if panel.is_busy:
            ans = QMessageBox.question(
                self,
                "关闭标签",
                "该标签正在执行。关闭将请求中止任务，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            panel.request_cancel_and_stop(wait_ms=5000)

        if self.tabs.count() <= 1:
            panel.reset_for_reuse()
            self._sync_tab_title(panel)
            return

        self.tabs.removeTab(index)
        panel.deleteLater()
