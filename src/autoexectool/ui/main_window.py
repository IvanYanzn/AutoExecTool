from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class _PageScroll(QScrollArea):
    """滚动容器：不把子页面的最小尺寸向上传递，避免主窗口无法缩小。"""

    def __init__(self, page: QWidget) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWidget(page)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(960, 640)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 0)

from autoexectool import APP_NAME_EN, APP_NAME_ZH, __version__
from autoexectool.app.container import AppContainer
from autoexectool.ui.pages.assets_page import AssetsPage
from autoexectool.ui.pages.home_page import HomePage
from autoexectool.ui.pages.hosts_page import HostsPage
from autoexectool.ui.pages.playbook_page import PlaybookPage
from autoexectool.ui.pages.publish_page import PublishPage
from autoexectool.ui.pages.run_page import RunPage
from autoexectool.ui.pages.schedule_page import SchedulePage
from autoexectool.ui.pages.sessions_page import SessionsPage
from autoexectool.ui.pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, container: AppContainer) -> None:
        super().__init__()
        self.container = container
        self.setWindowTitle(f"{APP_NAME_ZH} {__version__}")
        # 默认尺寸；显式最小尺寸，避免被「最宽页面」撑死无法缩小
        self.resize(1180, 760)
        self.setMinimumSize(860, 540)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav = QFrame()
        nav.setObjectName("NavPanel")
        nav.setFixedWidth(210)
        nav.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        nav_layout = QVBoxLayout(nav)
        brand = QLabel(APP_NAME_ZH)
        brand.setObjectName("TitleLabel")
        brand.setWordWrap(True)
        nav_layout.addWidget(brand)
        subtitle = QLabel(f"{APP_NAME_EN} · 编排执行")
        subtitle.setObjectName("MutedLabel")
        nav_layout.addWidget(subtitle)

        self.nav_buttons: list[QPushButton] = []
        labels = [
            "首页",
            "执行流程",
            "流程编排",
            "执行记录",
            "主机与凭证",
            "变量与指令组",
            "发布中心",
            "任务调度",
            "系统设置",
        ]
        for text in labels:
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        nav_layout.addStretch(1)
        layout.addWidget(nav)

        right = QVBoxLayout()
        self.stack = QStackedWidget()
        # 各页包进可滚动区域：内容再宽也能缩小窗口（出现滚动条）
        pages = [
            HomePage(container),
            RunPage(container),
            PlaybookPage(container),
            SessionsPage(container),
            HostsPage(container),
            AssetsPage(container),
            PublishPage(container),
            SchedulePage(container),
            SettingsPage(container),
        ]
        for p in pages:
            self.stack.addWidget(_PageScroll(p))
        right.addWidget(self.stack)
        layout.addLayout(right, 1)

        for i, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda _=False, idx=i: self._goto(idx))
        self._goto(0)

        plugins = ", ".join(container.loaded_plugins) or "无"
        self.statusBar().showMessage(
            f"数据目录：{container.paths.root} | 插件：{plugins}"
        )

        # 主密码仅在保存/使用远程加密凭证时需要，启动时不打断用户

    def _goto(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == index)
