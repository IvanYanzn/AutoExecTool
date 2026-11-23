from __future__ import annotations

import base64
from pathlib import Path

from autoexectool.connectors.base import ExecResult, RemoteSession
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import Credential, Host


class WinRmConnector:
    """WinRM 连接器：命令执行 + 基于 PowerShell 的文件上传/下载。"""

    protocol = "winrm"

    def connect(self, host: Host, credential: Credential | None) -> RemoteSession:
        if credential is None:
            raise AppError(ErrorCode.AUTH_FAILED, "WinRM 连接需要凭证。")
        try:
            import winrm  # type: ignore
        except ImportError as exc:
            raise AppError(
                ErrorCode.PLUGIN_LOAD_ERROR,
                "未安装 pywinrm，无法使用 WinRM。",
            ) from exc

        port = host.port or 5985
        # 5986 常见为 HTTPS
        scheme = "https" if port == 5986 else "http"
        endpoint = f"{scheme}://{host.address}:{port}/wsman"
        try:
            session = winrm.Session(
                endpoint,
                auth=(credential.username, credential.password),
                transport="ntlm",
            )
            result = session.run_ps("$env:COMPUTERNAME")
            if result.status_code != 0:
                err = (
                    result.std_err.decode("utf-8", "replace")
                    if result.std_err
                    else "auth/probe failed"
                )
                raise AppError(ErrorCode.AUTH_FAILED, detail=err)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.HOST_UNREACHABLE, detail=str(exc)) from exc
        return RemoteSession(host=host, handle=session)

    def exec(
        self,
        session: RemoteSession,
        command: str,
        timeout: float | None = None,
        cancel=None,
    ) -> ExecResult:
        _ = timeout
        _ = cancel
        winrm_session = session.handle
        try:
            result = winrm_session.run_ps(command)
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.STEP_FAILED, detail=str(exc)) from exc
        stdout = result.std_out.decode("utf-8", errors="replace") if result.std_out else ""
        stderr = result.std_err.decode("utf-8", errors="replace") if result.std_err else ""
        return ExecResult(exit_code=int(result.status_code), stdout=stdout, stderr=stderr)

    def upload(self, session: RemoteSession, local: Path, remote: str) -> None:
        data = local.read_bytes()
        # 分块写入，避免超大单命令
        chunk_size = 24_000
        remote_ps = remote.replace("'", "''")
        init = (
            f"$p = '{remote_ps}'; "
            f"$dir = Split-Path -Parent $p; "
            f"if ($dir -and -not (Test-Path $dir)) {{ New-Item -ItemType Directory -Path $dir -Force | Out-Null }}; "
            f"Set-Content -Path $p -Value ([byte[]]@()) -Encoding Byte"
        )
        result = self.exec(session, init)
        if result.exit_code != 0:
            raise AppError(ErrorCode.STEP_FAILED, "WinRM 上传初始化失败", detail=result.stderr)

        for i in range(0, len(data), chunk_size):
            chunk = data[i : i + chunk_size]
            b64 = base64.b64encode(chunk).decode("ascii")
            append = (
                f"$b = [Convert]::FromBase64String('{b64}'); "
                f"$fs = [System.IO.File]::Open('{remote_ps}', [System.IO.FileMode]::Append); "
                f"$fs.Write($b, 0, $b.Length); $fs.Close()"
            )
            result = self.exec(session, append)
            if result.exit_code != 0:
                raise AppError(ErrorCode.STEP_FAILED, "WinRM 上传失败", detail=result.stderr)

    def download(self, session: RemoteSession, remote: str, local: Path) -> None:
        remote_ps = remote.replace("'", "''")
        # 读取为 base64
        ps = (
            f"if (-not (Test-Path '{remote_ps}')) {{ throw 'remote missing' }}; "
            f"[Convert]::ToBase64String([IO.File]::ReadAllBytes('{remote_ps}'))"
        )
        result = self.exec(session, ps)
        if result.exit_code != 0:
            raise AppError(ErrorCode.STEP_FAILED, "WinRM 下载失败", detail=result.stderr)
        raw = "".join(result.stdout.split())
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(base64.b64decode(raw))

    def disconnect(self, session: RemoteSession) -> None:
        return None
