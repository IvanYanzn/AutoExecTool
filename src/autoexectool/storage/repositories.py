from __future__ import annotations

import json
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from autoexectool.domain.enums import OsType, ProtocolType
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import Credential, Host, HostGroup
from autoexectool.security.crypto import CredentialVault
from autoexectool.storage.models import (
    CommandGroupRow,
    CredentialRow,
    HostGroupMemberRow,
    HostGroupRow,
    HostRow,
    VariableSetRow,
)


class HostRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[Host]:
        rows = self.session.scalars(select(HostRow).order_by(HostRow.name)).all()
        return [self._to_domain(r) for r in rows]

    def get(self, host_id: str) -> Host:
        row = self.session.get(HostRow, host_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"主机不存在：{host_id}")
        return self._to_domain(row)

    def save(self, host: Host) -> Host:
        row = self.session.get(HostRow, host.id)
        if row is None:
            row = HostRow(id=host.id or str(uuid.uuid4()))
            self.session.add(row)
            host.id = row.id
        row.name = host.name
        row.address = host.address
        row.port = host.port
        row.os_type = host.os_type.value
        row.protocol = host.protocol.value
        row.credential_id = host.credential_id
        row.tags_json = json.dumps(host.tags, ensure_ascii=False)
        row.remark = host.remark
        self.session.commit()
        return host

    def delete(self, host_id: str) -> None:
        row = self.session.get(HostRow, host_id)
        if row is None:
            return
        self.session.delete(row)
        self.session.commit()

    @staticmethod
    def _to_domain(row: HostRow) -> Host:
        tags: list[str]
        try:
            tags = json.loads(row.tags_json or "[]")
        except json.JSONDecodeError:
            tags = []
        return Host(
            id=row.id,
            name=row.name,
            address=row.address,
            port=row.port,
            os_type=OsType(row.os_type),
            protocol=ProtocolType(row.protocol),
            credential_id=row.credential_id,
            tags=tags,
            remark=row.remark or "",
        )


class HostGroupRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[HostGroup]:
        rows = self.session.scalars(select(HostGroupRow).order_by(HostGroupRow.name)).all()
        return [self._to_domain(r) for r in rows]

    def get(self, group_id: str) -> HostGroup:
        row = self.session.get(HostGroupRow, group_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"主机组不存在：{group_id}")
        return self._to_domain(row)

    def get_by_name(self, name: str) -> HostGroup:
        row = self.session.scalars(
            select(HostGroupRow).where(HostGroupRow.name == name)
        ).first()
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"主机组不存在：{name}")
        return self._to_domain(row)

    def save(self, group: HostGroup) -> HostGroup:
        row = self.session.get(HostGroupRow, group.id) if group.id else None
        if row is None:
            existing = self.session.scalars(
                select(HostGroupRow).where(HostGroupRow.name == group.name)
            ).first()
            if existing is not None:
                row = existing
                group.id = existing.id
            else:
                row = HostGroupRow(id=group.id or str(uuid.uuid4()), name=group.name)
                self.session.add(row)
                group.id = row.id
        row.name = group.name
        row.remark = group.remark
        self.session.flush()  # 确保组行先落库，再写成员 FK
        # 重建成员
        old = self.session.scalars(
            select(HostGroupMemberRow).where(HostGroupMemberRow.group_id == row.id)
        ).all()
        for m in old:
            self.session.delete(m)
        self.session.flush()
        for hid in group.host_ids:
            # 校验主机存在
            if self.session.get(HostRow, hid) is None:
                raise AppError(ErrorCode.VALIDATION_ERROR, f"主机不存在：{hid}")
            self.session.add(HostGroupMemberRow(group_id=row.id, host_id=hid))
        self.session.commit()
        return group

    def delete(self, group_id: str) -> None:
        members = self.session.scalars(
            select(HostGroupMemberRow).where(HostGroupMemberRow.group_id == group_id)
        ).all()
        for m in members:
            self.session.delete(m)
        row = self.session.get(HostGroupRow, group_id)
        if row is not None:
            self.session.delete(row)
        self.session.commit()

    def list_hosts(self, group_id: str) -> list[Host]:
        group = self.get(group_id)
        repo = HostRepository(self.session)
        hosts: list[Host] = []
        for hid in group.host_ids:
            try:
                hosts.append(repo.get(hid))
            except AppError:
                continue
        return hosts

    def _to_domain(self, row: HostGroupRow) -> HostGroup:
        members = self.session.scalars(
            select(HostGroupMemberRow).where(HostGroupMemberRow.group_id == row.id)
        ).all()
        return HostGroup(
            id=row.id,
            name=row.name,
            remark=row.remark or "",
            host_ids=[m.host_id for m in members],
        )


class CredentialRepository:
    def __init__(self, session: Session, vault: CredentialVault) -> None:
        self.session = session
        self.vault = vault

    def list_meta(self) -> list[tuple[str, str, str]]:
        rows = self.session.scalars(select(CredentialRow).order_by(CredentialRow.name)).all()
        return [(r.id, r.name, r.auth_type) for r in rows]

    def get_decrypted(self, credential_id: str) -> Credential:
        row = self.session.get(CredentialRow, credential_id)
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"凭证不存在：{credential_id}")
        payload = self.vault.decrypt_payload(row.ciphertext)
        return Credential(
            id=row.id,
            name=row.name,
            auth_type=row.auth_type,
            username=str(payload.get("username") or ""),
            password=str(payload.get("password") or ""),
            private_key_pem=str(payload.get("private_key_pem") or ""),
            private_key_passphrase=str(payload.get("private_key_passphrase") or ""),
        )

    def save(self, cred: Credential) -> Credential:
        ciphertext = self.vault.encrypt_payload(
            {
                "username": cred.username,
                "password": cred.password,
                "private_key_pem": cred.private_key_pem,
                "private_key_passphrase": cred.private_key_passphrase,
            }
        )
        row = self.session.get(CredentialRow, cred.id) if cred.id else None
        if row is None:
            row = CredentialRow(id=cred.id or str(uuid.uuid4()))
            self.session.add(row)
            cred.id = row.id
        row.name = cred.name
        row.auth_type = cred.auth_type
        row.ciphertext = ciphertext
        self.session.commit()
        return cred

    def delete(self, credential_id: str) -> None:
        row = self.session.get(CredentialRow, credential_id)
        if row is None:
            return
        self.session.delete(row)
        self.session.commit()


class CommandGroupRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> Sequence[CommandGroupRow]:
        return self.session.scalars(select(CommandGroupRow).order_by(CommandGroupRow.name)).all()

    def get_content(self, name: str) -> dict:
        row = self.session.scalars(
            select(CommandGroupRow).where(CommandGroupRow.name == name)
        ).first()
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"指令组不存在：{name}")
        return json.loads(row.content_json)

    def save(self, name: str, content: dict, description: str = "") -> str:
        row = self.session.scalars(
            select(CommandGroupRow).where(CommandGroupRow.name == name)
        ).first()
        if row is None:
            row = CommandGroupRow(id=str(uuid.uuid4()), name=name)
            self.session.add(row)
        row.content_json = json.dumps(content, ensure_ascii=False)
        row.description = description
        self.session.commit()
        return row.id


class VariableSetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> Sequence[VariableSetRow]:
        return self.session.scalars(select(VariableSetRow).order_by(VariableSetRow.name)).all()

    def get_vars(self, name: str) -> dict:
        row = self.session.scalars(
            select(VariableSetRow).where(VariableSetRow.name == name)
        ).first()
        if row is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, f"变量集不存在：{name}")
        return json.loads(row.vars_json)

    def save(self, name: str, variables: dict, description: str = "") -> str:
        row = self.session.scalars(
            select(VariableSetRow).where(VariableSetRow.name == name)
        ).first()
        if row is None:
            row = VariableSetRow(id=str(uuid.uuid4()), name=name)
            self.session.add(row)
        row.vars_json = json.dumps(variables, ensure_ascii=False)
        row.description = description
        self.session.commit()
        return row.id
