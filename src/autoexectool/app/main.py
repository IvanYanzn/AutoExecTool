from __future__ import annotations

import sys

from autoexectool.app.container import build_container
from autoexectool.app.single_instance import SingleInstanceLock
from autoexectool.logging.setup import get_logger, setup_logging


def run_gui() -> None:
    container = build_container()
    setup_logging(container.paths.logs_app)
    logger = get_logger("app")
    lock = SingleInstanceLock(container.paths.tmp / "autoexectool.lock")
    try:
        lock.acquire()
    except Exception as exc:  # noqa: BLE001
        logger.error("%s", exc)
        # 无控制台（绿色包 / pythonw）时用弹窗提示
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "AutoExecTool", str(exc))
        except Exception:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
        sys.exit(1)

    from PySide6.QtWidgets import QApplication

    from autoexectool.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    from autoexectool import APP_NAME_ZH

    app.setApplicationName(APP_NAME_ZH)
    app.setOrganizationName(APP_NAME_ZH)

    from autoexectool.ui.theme.apply import apply_theme

    apply_theme(app)

    # 后台 Cron 调度
    container.scheduler.start_background(interval_sec=30.0)

    window = MainWindow(container)
    window.show()
    code = app.exec()
    container.scheduler.stop()
    lock.release()
    sys.exit(code)
