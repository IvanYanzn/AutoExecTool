from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from autoexectool.connectors.base import ExecResult, RemoteSession
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import Credential, Host


def _kill_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.kill()
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _drain_pipe(stream, bucket: list[str]) -> None:
    """持续读管道，避免子进程写满缓冲区后死锁。"""
    try:
        if stream is None:
            return
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            bucket.append(chunk)
    except Exception:  # noqa: BLE001
        pass


class LocalConnector:
    protocol = "local"

    def connect(self, host: Host, credential: Credential | None) -> RemoteSession:
        return RemoteSession(host=host, handle={"cwd": Path.cwd(), "proc": None})

    def exec(
        self,
        session: RemoteSession,
        command: str,
        timeout: float | None = None,
        cancel: threading.Event | None = None,
    ) -> ExecResult:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if isinstance(session.handle, dict):
            session.handle["proc"] = proc

        out_parts: list[str] = []
        err_parts: list[str] = []
        readers = [
            threading.Thread(
                target=_drain_pipe, args=(proc.stdout, out_parts), daemon=True
            ),
            threading.Thread(
                target=_drain_pipe, args=(proc.stderr, err_parts), daemon=True
            ),
        ]
        for t in readers:
            t.start()

        deadline = (time.monotonic() + float(timeout)) if timeout else None
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    _kill_process_tree(proc)
                    raise AppError(ErrorCode.CANCELLED, "本地命令已中止")
                if deadline is not None and time.monotonic() >= deadline:
                    _kill_process_tree(proc)
                    raise AppError(
                        ErrorCode.STEP_TIMEOUT,
                        f"步骤执行超时（已等待 {int(timeout)} 秒）。"
                        f"若构建仍在跑且未写满日志，请检查命令是否卡住；"
                        f"确需更长时间可增大 timeout_sec。",
                        detail=f"本地命令超时（{timeout}s）",
                    )
                rc = proc.poll()
                if rc is not None:
                    for t in readers:
                        t.join(timeout=5)
                    return ExecResult(
                        exit_code=int(rc),
                        stdout="".join(out_parts),
                        stderr="".join(err_parts),
                    )
                time.sleep(0.2)
        finally:
            if isinstance(session.handle, dict):
                session.handle["proc"] = None

    def upload(self, session: RemoteSession, local: Path, remote: str) -> None:
        dest = Path(remote)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)

    def download(self, session: RemoteSession, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(remote, local)

    def disconnect(self, session: RemoteSession) -> None:
        if isinstance(session.handle, dict):
            proc = session.handle.get("proc")
            if proc is not None:
                _kill_process_tree(proc)
                session.handle["proc"] = None
