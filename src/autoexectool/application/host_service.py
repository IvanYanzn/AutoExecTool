from __future__ import annotations

import csv
import platform
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from autoexectool.domain.enums import OsType, ProtocolType
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import Credential, Host, HostGroup
from autoexectool.storage.repositories import (
    CredentialRepository,
    HostGroupRepository,
    HostRepository,
)

if TYPE_CHECKING:
    from autoexectool.app.container import AppContainer


class HostService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def list_hosts(self) -> list[Host]:
        with self.container.session_factory() as session:
            return HostRepository(session).list()

    def resolve_by_ref(self, ref: str) -> tuple[Host, Credential | None]:
        """按步骤 host 引用解析库存主机及其绑定凭证。

        支持：``local`` / ``本机`` / ``@local``、主机 id、主机名称（须唯一）。
        """
        key = (ref or "").strip()
        if not key:
            raise AppError(ErrorCode.VALIDATION_ERROR, "主机引用为空")

        with self.container.session_factory() as session:
            repo = HostRepository(session)
            host: Host | None = None
            lowered = key.lower()
            if lowered in {"local", "本机", "@local"}:
                for h in repo.list():
                    if h.protocol == ProtocolType.LOCAL:
                        host = h
                        break
                if host is None:
                    host = Host(
                        id=str(uuid.uuid4()),
                        name="本机",
                        address="127.0.0.1",
                        port=0,
                        os_type=OsType.WINDOWS
                        if platform.system() == "Windows"
                        else OsType.LINUX,
                        protocol=ProtocolType.LOCAL,
                    )
                    host = repo.save(host)
            else:
                try:
                    host = repo.get(key)
                except AppError:
                    matches = [h for h in repo.list() if h.name == key]
                    if len(matches) == 1:
                        host = matches[0]
                    elif len(matches) > 1:
                        raise AppError(
                            ErrorCode.VALIDATION_ERROR,
                            f"主机名称不唯一：{key}（请改用主机 id）",
                        ) from None
                    else:
                        raise AppError(
                            ErrorCode.VALIDATION_ERROR,
                            f"未找到主机：{key}（请在「主机与凭证」中配置，或使用 id/名称/local）",
                        ) from None

            cred: Credential | None = None
            if host.credential_id:
                try:
                    cred = CredentialRepository(
                        session, self.container.vault
                    ).get_decrypted(host.credential_id)
                except Exception as exc:  # noqa: BLE001
                    raise AppError(
                        ErrorCode.VALIDATION_ERROR,
                        f"主机「{host.name}」凭证不可用：{exc}",
                    ) from exc
            return host, cred

    def upsert_host(
        self,
        *,
        name: str,
        address: str,
        protocol: str,
        os_type: str,
        port: int | None = None,
        credential_id: str | None = None,
        remark: str = "",
        host_id: str | None = None,
    ) -> Host:
        proto = ProtocolType(protocol)
        default_port = 22 if proto == ProtocolType.SSH else (5985 if proto == ProtocolType.WINRM else 0)
        host = Host(
            id=host_id or str(uuid.uuid4()),
            name=name,
            address=address,
            port=port if port is not None else default_port,
            os_type=OsType(os_type),
            protocol=proto,
            credential_id=credential_id,
            remark=remark,
        )
        with self.container.session_factory() as session:
            return HostRepository(session).save(host)

    def delete_host(self, host_id: str) -> None:
        with self.container.session_factory() as session:
            HostRepository(session).delete(host_id)

    def list_credentials(self) -> list[tuple[str, str, str]]:
        with self.container.session_factory() as session:
            return CredentialRepository(session, self.container.vault).list_meta()

    def save_credential(
        self,
        *,
        name: str,
        auth_type: str,
        username: str = "",
        password: str = "",
        private_key_pem: str = "",
        credential_id: str | None = None,
        keep_password_if_empty: bool = False,
    ) -> Credential:
        if not self.container.master_keys.is_unlocked:
            raise AppError(ErrorCode.NOT_INITIALIZED, "请先解锁主密码后再保存凭证。")
        cid = credential_id or str(uuid.uuid4())
        existing_key = ""
        existing_passphrase = ""
        existing_password = ""
        existing_auth = auth_type
        if credential_id:
            with self.container.session_factory() as session:
                old = CredentialRepository(session, self.container.vault).get_decrypted(
                    credential_id
                )
            existing_key = old.private_key_pem
            existing_passphrase = old.private_key_passphrase
            existing_password = old.password
            existing_auth = old.auth_type
            if auth_type == "password" and keep_password_if_empty and not password:
                password = existing_password
            if auth_type == "ssh_key" and not private_key_pem:
                private_key_pem = existing_key
        cred = Credential(
            id=cid,
            name=name,
            auth_type=auth_type or existing_auth,
            username=username,
            password=password,
            private_key_pem=private_key_pem or existing_key,
            private_key_passphrase=existing_passphrase,
        )
        with self.container.session_factory() as session:
            return CredentialRepository(session, self.container.vault).save(cred)

    def get_credential(self, credential_id: str) -> Credential:
        if not self.container.master_keys.is_unlocked:
            raise AppError(ErrorCode.NOT_INITIALIZED, "请先解锁主密码。")
        with self.container.session_factory() as session:
            return CredentialRepository(session, self.container.vault).get_decrypted(
                credential_id
            )

    def delete_credential(self, credential_id: str) -> None:
        if not self.container.master_keys.is_unlocked:
            raise AppError(ErrorCode.NOT_INITIALIZED, "请先解锁主密码后再删除凭证。")
        with self.container.session_factory() as session:
            # 解除主机绑定
            for host in HostRepository(session).list():
                if host.credential_id == credential_id:
                    host.credential_id = None
                    HostRepository(session).save(host)
            CredentialRepository(session, self.container.vault).delete(credential_id)
        pub = self.container.paths.keys / f"{credential_id}.pub"
        if pub.exists():
            try:
                pub.unlink()
            except OSError:
                pass

    def export_csv(self, path: Path) -> int:
        hosts = self.list_hosts()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "name",
                    "address",
                    "port",
                    "os_type",
                    "protocol",
                    "credential_id",
                    "remark",
                ],
            )
            writer.writeheader()
            for h in hosts:
                writer.writerow(
                    {
                        "id": h.id,
                        "name": h.name,
                        "address": h.address,
                        "port": h.port,
                        "os_type": h.os_type.value,
                        "protocol": h.protocol.value,
                        "credential_id": h.credential_id or "",
                        "remark": h.remark,
                    }
                )
        return len(hosts)

    def import_csv(self, path: Path) -> int:
        if not path.exists():
            raise AppError(ErrorCode.VALIDATION_ERROR, f"CSV 不存在：{path}")
        count = 0
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.upsert_host(
                    name=row["name"].strip(),
                    address=row["address"].strip(),
                    protocol=row.get("protocol") or "ssh",
                    os_type=row.get("os_type") or "linux",
                    port=int(row["port"]) if row.get("port") else None,
                    credential_id=row.get("credential_id") or None,
                    remark=row.get("remark") or "",
                    host_id=row.get("id") or None,
                )
                count += 1
        return count

    def list_host_groups(self) -> list[HostGroup]:
        with self.container.session_factory() as session:
            return HostGroupRepository(session).list()

    def upsert_host_group(
        self,
        *,
        name: str,
        host_ids: list[str] | None = None,
        remark: str = "",
        group_id: str | None = None,
    ) -> HostGroup:
        group = HostGroup(
            id=group_id or str(uuid.uuid4()),
            name=name,
            remark=remark,
            host_ids=list(host_ids or []),
        )
        with self.container.session_factory() as session:
            return HostGroupRepository(session).save(group)

    def delete_host_group(self, group_id: str) -> None:
        with self.container.session_factory() as session:
            HostGroupRepository(session).delete(group_id)

    def list_group_hosts(self, group_id: str) -> list[Host]:
        with self.container.session_factory() as session:
            return HostGroupRepository(session).list_hosts(group_id)

    def resolve_hosts_with_credentials(
        self, *, host_id: str | None = None, group_id: str | None = None
    ) -> list[tuple[Host, Credential | None]]:
        """解析执行目标：单机或主机组，附带解密凭证（若已解锁）。"""
        with self.container.session_factory() as session:
            hosts: list[Host]
            if group_id:
                hosts = HostGroupRepository(session).list_hosts(group_id)
            elif host_id:
                hosts = [HostRepository(session).get(host_id)]
            else:
                raise AppError(ErrorCode.VALIDATION_ERROR, "请指定 host_id 或 group_id")
            result: list[tuple[Host, Credential | None]] = []
            cred_repo = CredentialRepository(session, self.container.vault)
            for h in hosts:
                cred = None
                if h.credential_id:
                    if not self.container.master_keys.is_unlocked:
                        raise AppError(
                            ErrorCode.NOT_INITIALIZED,
                            "目标主机含凭证，请先解锁主密码。",
                        )
                    cred = cred_repo.get_decrypted(h.credential_id)
                result.append((h, cred))
            return result

    def bind_credential(self, host_id: str, credential_id: str | None) -> Host:
        with self.container.session_factory() as session:
            host = HostRepository(session).get(host_id)
        return self.upsert_host(
            name=host.name,
            address=host.address,
            protocol=host.protocol.value,
            os_type=host.os_type.value,
            port=host.port,
            credential_id=credential_id or None,
            remark=host.remark,
            host_id=host.id,
        )

    def generate_ssh_key_credential(
        self,
        *,
        name: str,
        username: str,
        comment: str = "autoexectool",
    ) -> tuple[Credential, Path, str]:
        """生成 Ed25519 密钥凭证：私钥进保险库，公钥写入 data/config/keys/*.pub。"""
        from autoexectool.security.ssh_keys import (
            generate_ed25519_keypair,
            write_public_key_file,
        )

        if not name.strip():
            raise AppError(ErrorCode.VALIDATION_ERROR, "请填写凭证名")
        if not username.strip():
            raise AppError(ErrorCode.VALIDATION_ERROR, "请填写用户名（如 deploy）")
        private_pem, public_line = generate_ed25519_keypair(comment=comment)
        cred = self.save_credential(
            name=name.strip(),
            auth_type="ssh_key",
            username=username.strip(),
            private_key_pem=private_pem,
        )
        pub_path = self.container.paths.keys / f"{cred.id}.pub"
        write_public_key_file(pub_path, public_line)
        return cred, pub_path, public_line

    def get_credential_public_key(self, credential_id: str) -> tuple[str, Path | None]:
        """返回 (公钥行, 公钥文件路径或 None)。"""
        from autoexectool.security.ssh_keys import (
            public_key_from_private_pem,
            write_public_key_file,
        )

        if not self.container.master_keys.is_unlocked:
            raise AppError(ErrorCode.NOT_INITIALIZED, "请先解锁主密码。")
        with self.container.session_factory() as session:
            cred = CredentialRepository(session, self.container.vault).get_decrypted(
                credential_id
            )
        if not cred.private_key_pem:
            raise AppError(ErrorCode.VALIDATION_ERROR, "该凭证不是密钥类型，或无私钥。")
        pub_path = self.container.paths.keys / f"{cred.id}.pub"
        if pub_path.exists():
            return pub_path.read_text(encoding="utf-8").strip(), pub_path
        line = public_key_from_private_pem(
            cred.private_key_pem,
            cred.private_key_passphrase or "",
            comment=cred.name or "autoexectool",
        )
        write_public_key_file(pub_path, line)
        return line, pub_path

    def install_public_key_to_host(
        self,
        *,
        host_id: str,
        key_credential_id: str,
        password_credential_id: str | None = None,
    ) -> str:
        """用密码凭证登录主机，把密钥凭证的公钥写入 ~/.ssh/authorized_keys。"""
        if not self.container.master_keys.is_unlocked:
            raise AppError(ErrorCode.NOT_INITIALIZED, "请先解锁主密码。")
        with self.container.session_factory() as session:
            host = HostRepository(session).get(host_id)
            cred_repo = CredentialRepository(session, self.container.vault)
            key_cred = cred_repo.get_decrypted(key_credential_id)
            if password_credential_id:
                pass_cred = cred_repo.get_decrypted(password_credential_id)
            elif host.credential_id and host.credential_id != key_credential_id:
                pass_cred = cred_repo.get_decrypted(host.credential_id)
            else:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "安装公钥需要一台密码凭证：请指定密码凭证，或先把密码凭证绑定到该主机。",
                )
        if host.protocol != ProtocolType.SSH:
            raise AppError(ErrorCode.VALIDATION_ERROR, "仅支持 SSH 主机安装公钥")
        if not key_cred.private_key_pem:
            raise AppError(ErrorCode.VALIDATION_ERROR, "选中的密钥凭证无私钥")
        if not pass_cred.password:
            raise AppError(ErrorCode.VALIDATION_ERROR, "安装公钥需要密码凭证（含密码）")

        from autoexectool.security.ssh_keys import remote_install_authorized_key_script

        public_line, _ = self.get_credential_public_key(key_credential_id)
        self._ssh_run_as(
            host,
            pass_cred,
            remote_install_authorized_key_script(public_line),
            fail_message="安装工具密钥公钥失败",
        )

        # 安装成功后，把主机绑定到密钥凭证，后续免密
        self.bind_credential(host_id, key_credential_id)
        return f"公钥已写入 {host.address}，主机已绑定密钥凭证「{key_cred.name}」。"

    def setup_openssh_passwordless(
        self,
        *,
        host_id: str,
        password_credential_id: str | None = None,
    ) -> str:
        """为本机 OpenSSH（方案 A 的 ssh/scp）配置到选中主机的免密登录。

        1) 若无则生成 %USERPROFILE%\\.ssh\\id_ed25519
        2) 用密码凭证登录，把该公钥写入远端 authorized_keys
        """
        from autoexectool.security.ssh_keys import (
            ensure_user_openssh_ed25519,
            remote_install_authorized_key_script,
        )

        if not self.container.master_keys.is_unlocked:
            raise AppError(ErrorCode.NOT_INITIALIZED, "请先解锁主密码。")
        with self.container.session_factory() as session:
            host = HostRepository(session).get(host_id)
            if host.protocol != ProtocolType.SSH:
                raise AppError(ErrorCode.VALIDATION_ERROR, "仅支持 SSH 主机")
            cred_repo = CredentialRepository(session, self.container.vault)
            pass_cred = None
            candidates: list[str] = []
            if password_credential_id:
                candidates.append(password_credential_id)
            if host.credential_id and host.credential_id not in candidates:
                candidates.append(host.credential_id)
            for cid, _name, auth in self.list_credentials():
                if auth == "password" and cid not in candidates:
                    candidates.append(cid)
            for cid in candidates:
                c = cred_repo.get_decrypted(cid)
                if c.password:
                    pass_cred = c
                    break
            if pass_cred is None:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "配置本机 OpenSSH 免密需要一条「密码」凭证（与 Xshell 相同）。"
                    "请先保存密码凭证，建议绑定到该主机后再点此按钮。",
                )

        priv, pub, public_line, created = ensure_user_openssh_ed25519(
            comment=f"autoexectool@{host.address}"
        )
        self._ssh_run_as(
            host,
            pass_cred,
            remote_install_authorized_key_script(public_line),
            fail_message="安装本机 OpenSSH 公钥到远端失败",
        )
        created_tip = "已新生成本机密钥对；" if created else "已使用本机已有密钥；"
        return (
            f"{created_tip}公钥已写入 {pass_cred.username}@{host.address}。\n"
            f"本机私钥：{priv}\n本机公钥：{pub}\n\n"
            "请在本机验证：\n"
            f'  ssh -o BatchMode=yes {pass_cred.username}@{host.address} "echo ok"\n'
            "通过后即可在「执行流程」中选目标「本机」，跑依赖本机 ssh/scp 的编排。"
        )

    def _ssh_run_as(self, host: Host, credential: Credential, script: str, *, fail_message: str) -> None:
        connector = self.container.connectors.get("ssh")
        remote = connector.connect(host, credential)
        try:
            result = connector.exec(remote, script, timeout=30)
            if result.exit_code != 0 or "installed_ok" not in (result.stdout or ""):
                raise AppError(
                    ErrorCode.STEP_FAILED,
                    fail_message,
                    detail=(result.stderr or result.stdout or "")[:800],
                )
        finally:
            connector.disconnect(remote)

    def test_connection(self, host_id: str) -> str:
        with self.container.session_factory() as session:
            host = HostRepository(session).get(host_id)
            cred = None
            if host.credential_id:
                if not self.container.master_keys.is_unlocked:
                    raise AppError(ErrorCode.NOT_INITIALIZED, "测试远程连接前请先解锁主密码。")
                cred = CredentialRepository(session, self.container.vault).get_decrypted(
                    host.credential_id
                )
        connector = self.container.connectors.get(host.protocol.value)
        remote = connector.connect(host, cred)
        try:
            if host.protocol == ProtocolType.LOCAL:
                result = connector.exec(remote, "echo AutoExecTool-ok")
            elif host.os_type == OsType.WINDOWS:
                result = connector.exec(remote, "hostname")
            else:
                result = connector.exec(remote, "hostname")
            if result.exit_code != 0:
                raise AppError(
                    ErrorCode.HOST_UNREACHABLE,
                    detail=(result.stderr or result.stdout)[:500],
                )
            return (result.stdout or "ok").strip() or "连接成功"
        finally:
            connector.disconnect(remote)
