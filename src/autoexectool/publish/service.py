from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from autoexectool.app.container import AppContainer
from autoexectool.domain.enums import ExecutionStatus, OsType, ProtocolType
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import Host
from autoexectool.orchestrator.loader import load_playbook_yaml
from autoexectool.publish.repository import PublishRepository
from autoexectool.storage.repositories import CredentialRepository, HostRepository


class PublishService:
    """发布中心：应用/环境/制品、发布执行、一键回滚。"""

    def __init__(self, container: AppContainer) -> None:
        self.container = container
        from autoexectool.runtime_paths import templates_dir

        self.templates_dir = templates_dir()

    def ensure_demo_app(self) -> tuple[str, str, str]:
        """创建本地演示应用/环境/制品，返回 (app_id, env_id, package_id)。"""
        packages_root = self.container.paths.packages
        apps_root = self.container.paths.tmp / "apps"
        apps_root.mkdir(parents=True, exist_ok=True)
        deploy_dir = apps_root / "demo-api"
        deploy_dir.mkdir(parents=True, exist_ok=True)

        pkg_dir = packages_root / "demo-api" / "1.0.0"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        marker = pkg_dir / "APP_VERSION.txt"
        marker.write_text("1.0.0\n", encoding="utf-8")
        (pkg_dir / "README.txt").write_text("demo package\n", encoding="utf-8")

        with self.container.session_factory() as session:
            repo = PublishRepository(session)
            app = repo.save_app(
                name="demo-api",
                app_type="dir",
                description="本地目录发布演示",
                deploy_dir=str(deploy_dir),
            )
            # local host
            host_repo = HostRepository(session)
            hosts = host_repo.list()
            local = next((h for h in hosts if h.protocol == ProtocolType.LOCAL), None)
            if local is None:
                local = Host(
                    id="local-default",
                    name="本机",
                    address="127.0.0.1",
                    port=0,
                    os_type=OsType.WINDOWS if os.name == "nt" else OsType.LINUX,
                    protocol=ProtocolType.LOCAL,
                )
                host_repo.save(local)
            env = repo.save_env(name="local", app_id=app.id, host_id=local.id, variables={})
            checksum = hashlib.sha256(marker.read_bytes()).hexdigest()
            pkg = repo.save_package(
                app_id=app.id,
                version="1.0.0",
                path=str(pkg_dir),
                checksum=checksum,
                note="演示制品",
            )
            return app.id, env.id, pkg.id

    def list_apps(self):
        with self.container.session_factory() as session:
            return list(PublishRepository(session).list_apps())

    def list_envs(self, app_id: str):
        with self.container.session_factory() as session:
            return list(PublishRepository(session).list_envs(app_id))

    def list_packages(self, app_id: str):
        with self.container.session_factory() as session:
            return list(PublishRepository(session).list_packages(app_id))

    def list_records(self, app_id: str | None = None):
        with self.container.session_factory() as session:
            return list(PublishRepository(session).list_records(app_id=app_id))

    def create_app(self, name: str, deploy_dir: str, description: str = "") -> str:
        with self.container.session_factory() as session:
            row = PublishRepository(session).save_app(
                name=name, deploy_dir=deploy_dir, description=description
            )
            return row.id

    def create_env(self, app_id: str, name: str, host_id: str | None) -> str:
        with self.container.session_factory() as session:
            row = PublishRepository(session).save_env(
                name=name, app_id=app_id, host_id=host_id
            )
            return row.id

    def register_package(self, app_id: str, version: str, path: str, note: str = "") -> str:
        p = Path(path)
        if not p.exists():
            raise AppError(ErrorCode.VALIDATION_ERROR, f"制品路径不存在：{path}")
        checksum = ""
        if p.is_file():
            checksum = hashlib.sha256(p.read_bytes()).hexdigest()
        with self.container.session_factory() as session:
            row = PublishRepository(session).save_package(
                app_id=app_id, version=version, path=str(p), checksum=checksum, note=note
            )
            return row.id

    def deploy(
        self,
        *,
        app_id: str,
        env_id: str,
        package_id: str,
        dry_run: bool = False,
        operator: str = "",
    ) -> dict:
        with self.container.session_factory() as session:
            repo = PublishRepository(session)
            app = repo.get_app(app_id)
            env = repo.get_env(env_id)
            pkg = repo.get_package(package_id)
            if env.app_id != app.id or pkg.app_id != app.id:
                raise AppError(ErrorCode.VALIDATION_ERROR, "应用/环境/制品不匹配")

            host, credential = self._resolve_host(session, env.host_id)
            env_vars = json.loads(env.vars_json or "{}")

            backup_root = self.container.paths.backups / "releases" / app.name / env.name
            backup_root.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_ref = str(backup_root / f"{ts}_{pkg.version}")

            variables = {
                **env_vars,
                "APP_NAME": app.name,
                "DEPLOY_DIR": app.deploy_dir,
                "PACKAGE_PATH": pkg.path,
                "PACKAGE_VERSION": pkg.version,
                "BACKUP_REF": backup_ref,
            }

            playbook_path = self._pick_playbook("publish_dir_local.yaml")
            if dry_run:
                plan = self.container.orchestrator.dry_run(
                    load_playbook_yaml(playbook_path), host, variables=variables
                )
                return {"dry_run": True, "plan": plan, "backup_ref": backup_ref}

            record = repo.add_record(
                app_id=app.id,
                env_id=env.id,
                version=pkg.version,
                package_id=pkg.id,
                status="Running",
                backup_ref=backup_ref,
                operator=operator or os.getenv("USERNAME") or os.getenv("USER") or "",
                summary="发布中",
            )
            record_id = record.id

        session_id = self.container.orchestrator.start(
            load_playbook_yaml(playbook_path),
            host,
            credential=credential,
            variables=variables,
            dry_run=False,
        )
        runtime = self.container.orchestrator.get_status(session_id)
        status = (
            "Succeeded"
            if runtime.status == ExecutionStatus.SUCCEEDED
            else ("Cancelled" if runtime.status == ExecutionStatus.CANCELLED else "Failed")
        )
        with self.container.session_factory() as session:
            PublishRepository(session).update_record(
                record_id,
                session_id=session_id,
                status=status,
                summary=runtime.summary,
            )
        return {
            "record_id": record_id,
            "session_id": session_id,
            "status": status,
            "summary": runtime.summary,
            "backup_ref": backup_ref,
        }

    def rollback(
        self,
        *,
        app_id: str,
        env_id: str,
        dry_run: bool = False,
        operator: str = "",
    ) -> dict:
        with self.container.session_factory() as session:
            repo = PublishRepository(session)
            app = repo.get_app(app_id)
            env = repo.get_env(env_id)
            last = repo.latest_success(app_id, env_id)
            if last is None or not last.backup_ref:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "没有可回滚的成功发布记录或备份路径。",
                )
            if not Path(last.backup_ref).exists():
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    f"备份目录不存在：{last.backup_ref}",
                )
            host, credential = self._resolve_host(session, env.host_id)
            variables = {
                "APP_NAME": app.name,
                "DEPLOY_DIR": app.deploy_dir,
                "BACKUP_REF": last.backup_ref,
                "PACKAGE_VERSION": last.version,
            }
            playbook_path = self._pick_playbook("rollback_dir_local.yaml")
            if dry_run:
                plan = self.container.orchestrator.dry_run(
                    load_playbook_yaml(playbook_path), host, variables=variables
                )
                return {
                    "dry_run": True,
                    "plan": plan,
                    "from_version": last.version,
                    "backup_ref": last.backup_ref,
                }

            record = repo.add_record(
                app_id=app.id,
                env_id=env.id,
                version=f"rollback:{last.version}",
                package_id=last.package_id,
                status="Running",
                backup_ref=last.backup_ref,
                operator=operator or os.getenv("USERNAME") or os.getenv("USER") or "",
                summary="回滚中",
            )
            record_id = record.id

        session_id = self.container.orchestrator.start(
            load_playbook_yaml(playbook_path),
            host,
            credential=credential,
            variables=variables,
            dry_run=False,
        )
        runtime = self.container.orchestrator.get_status(session_id)
        status = (
            "Succeeded"
            if runtime.status == ExecutionStatus.SUCCEEDED
            else ("Cancelled" if runtime.status == ExecutionStatus.CANCELLED else "Failed")
        )
        with self.container.session_factory() as session:
            PublishRepository(session).update_record(
                record_id,
                session_id=session_id,
                status=status,
                summary=runtime.summary,
            )
        return {
            "record_id": record_id,
            "session_id": session_id,
            "status": status,
            "summary": runtime.summary,
            "from_version": last.version,
            "backup_ref": last.backup_ref,
        }

    def _resolve_host(self, session, host_id: str | None):
        if not host_id:
            # 默认本机
            host = Host(
                id="local-ephemeral",
                name="local",
                address="127.0.0.1",
                port=0,
                os_type=OsType.WINDOWS if os.name == "nt" else OsType.LINUX,
                protocol=ProtocolType.LOCAL,
            )
            return host, None
        host = HostRepository(session).get(host_id)
        credential = None
        if host.credential_id:
            if not self.container.master_keys.is_unlocked:
                raise AppError(ErrorCode.NOT_INITIALIZED, "发布前请先解锁主密码。")
            credential = CredentialRepository(session, self.container.vault).get_decrypted(
                host.credential_id
            )
        return host, credential

    def _pick_playbook(self, name: str) -> Path:
        """按文件名在 templates（含子目录）中查找。"""
        direct = self.templates_dir / name
        if direct.exists():
            return direct
        matches = sorted(self.templates_dir.rglob(name))
        files = [p for p in matches if p.is_file()]
        if not files:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"缺少发布模板：{name}（已在 {self.templates_dir} 下递归查找）",
            )
        return files[0]
