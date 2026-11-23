from __future__ import annotations

from pathlib import Path

import paramiko

from autoexectool.connectors.base import ExecResult, RemoteSession
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import Credential, Host
from autoexectool.logging.setup import get_logger

logger = get_logger("connectors.ssh")


class SshConnector:
    protocol = "ssh"

    def connect(self, host: Host, credential: Credential | None) -> RemoteSession:
        if credential is None:
            raise AppError(ErrorCode.AUTH_FAILED, "SSH 连接需要凭证。")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs: dict = {
            "hostname": host.address,
            "port": host.port or 22,
            "username": credential.username,
            "timeout": 15,
            "allow_agent": False,
            "look_for_keys": False,
        }
        try:
            if credential.private_key_pem:
                from autoexectool.security.ssh_keys import load_private_key

                connect_kwargs["pkey"] = load_private_key(
                    credential.private_key_pem,
                    credential.private_key_passphrase or "",
                )
            else:
                connect_kwargs["password"] = credential.password
            client.connect(**connect_kwargs)
        except paramiko.AuthenticationException as exc:
            raise AppError(ErrorCode.AUTH_FAILED) from exc
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.HOST_UNREACHABLE, detail=str(exc)) from exc
        return RemoteSession(host=host, handle=client)

    def exec(
        self,
        session: RemoteSession,
        command: str,
        timeout: float | None = None,
        cancel=None,
    ) -> ExecResult:
        _ = cancel
        client: paramiko.SSHClient = session.handle  # type: ignore[assignment]
        try:
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.STEP_FAILED, detail=str(exc)) from exc
        return ExecResult(exit_code=exit_code, stdout=out, stderr=err)

    def upload(self, session: RemoteSession, local: Path, remote: str) -> None:
        client: paramiko.SSHClient = session.handle  # type: ignore[assignment]
        sftp = client.open_sftp()
        try:
            sftp.put(str(local), remote)
        finally:
            sftp.close()

    def download(self, session: RemoteSession, remote: str, local: Path) -> None:
        client: paramiko.SSHClient = session.handle  # type: ignore[assignment]
        local.parent.mkdir(parents=True, exist_ok=True)
        sftp = client.open_sftp()
        try:
            sftp.get(remote, str(local))
        finally:
            sftp.close()

    def disconnect(self, session: RemoteSession) -> None:
        client: paramiko.SSHClient = session.handle  # type: ignore[assignment]
        client.close()
