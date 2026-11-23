from __future__ import annotations

from pathlib import Path

import typer
from rich import print as rprint

from autoexectool import __version__
from autoexectool.app.container import build_container
from autoexectool.application.host_service import HostService
from autoexectool.domain.enums import OsType, ProtocolType
from autoexectool.domain.models import Host
from autoexectool.logging.setup import setup_logging
from autoexectool.orchestrator.loader import load_playbook_yaml
from autoexectool.orchestrator.serialize import playbook_to_dict
from autoexectool.storage.repositories import (
    CommandGroupRepository,
    VariableSetRepository,
)

app = typer.Typer(
    name="autoexectool",
    help="通用自动化任务编排执行工具 AutoExecTool",
    no_args_is_help=True,
)
host_app = typer.Typer(help="主机管理")
hgroup_app = typer.Typer(help="主机组管理")
cred_app = typer.Typer(help="凭证管理")
publish_app = typer.Typer(help="发布中心")
app.add_typer(host_app, name="host")
app.add_typer(hgroup_app, name="host-group")
app.add_typer(cred_app, name="cred")
app.add_typer(publish_app, name="publish")


@app.callback()
def _root() -> None:
    """AutoExecTool CLI。"""


@app.command("version")
def version_cmd() -> None:
    """显示版本。"""
    rprint(f"AutoExecTool {__version__}")


@app.command("init-master")
def init_master(
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """初始化主密码（首次使用）。"""
    container = build_container()
    setup_logging(container.paths.logs_app)
    container.master_keys.initialize(password)
    rprint("[green]主密码已初始化。[/green]")


@app.command("unlock")
def unlock_master(
    password: str = typer.Option(..., prompt=True, hide_input=True),
) -> None:
    """解锁主密码（当前进程内有效；GUI 内另有解锁入口）。"""
    container = build_container()
    container.master_keys.unlock(password)
    rprint("[green]主密码已解锁（本命令主要用于校验；请在 GUI 中解锁以管理凭证）。[/green]")


@app.command("run")
def run_playbook(
    playbook: Path = typer.Argument(..., exists=True, readable=True, help="流程 YAML 路径"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只预览不执行变更"),
    address: str = typer.Option("127.0.0.1", help="目标地址（未指定 --host-id/--group-id 时使用）"),
    protocol: str = typer.Option("local", help="ssh|winrm|local"),
    os_type: str = typer.Option(
        "windows" if __import__("platform").system() == "Windows" else "linux"
    ),
    host_id: str | None = typer.Option(None, help="使用已保存主机 ID"),
    group_id: str | None = typer.Option(None, help="主机组 ID（对组内主机执行）"),
    var_set: str | None = typer.Option(None, help="变量集名称"),
    max_parallel: int = typer.Option(5, help="主机组并发上限"),
) -> None:
    """执行流程。"""
    import json

    container = build_container()
    setup_logging(container.paths.logs_app)
    spec = load_playbook_yaml(playbook)

    variables: dict = {}
    if var_set:
        with container.session_factory() as session:
            variables.update(VariableSetRepository(session).get_vars(var_set))

    svc = HostService(container)
    targets: list[tuple] = []
    if group_id or host_id:
        if not container.master_keys.is_unlocked and container.master_keys.is_initialized:
            password = typer.prompt("主密码（若目标含凭证）", hide_input=True, default="")
            if password:
                container.master_keys.unlock(password)
        targets = svc.resolve_hosts_with_credentials(host_id=host_id, group_id=group_id)
    else:
        targets = [
            (
                Host(
                    id="cli-ephemeral",
                    name="cli-target",
                    address=address,
                    port=22 if protocol == "ssh" else (5985 if protocol == "winrm" else 0),
                    os_type=OsType(os_type),
                    protocol=ProtocolType(protocol),
                ),
                None,
            )
        ]

    if dry_run:
        for host, _cred in targets:
            rprint(f"=== {host.name} ===")
            for line in container.orchestrator.dry_run(
                spec,
                host,
                variables=variables,
                playbook_path=str(playbook),
            ):
                rprint(line)
        return

    playbook_json = json.dumps(playbook_to_dict(spec), ensure_ascii=False)
    if len(targets) == 1:
        host, credential = targets[0]
        ids = [
            container.orchestrator.start(
                spec,
                host,
                credential=credential,
                variables=variables,
                dry_run=False,
                playbook_path=str(playbook),
                playbook_json=playbook_json,
            )
        ]
    else:
        ids = container.orchestrator.start_on_hosts(
            spec,
            targets,
            variables=variables,
            playbook_path=str(playbook),
            playbook_json=playbook_json,
            max_parallel=max_parallel,
        )
    for session_id in ids:
        runtime = container.orchestrator.get_status(session_id)
        rprint(f"会话：{session_id}")
        rprint(f"状态：{runtime.status}")
        rprint(f"摘要：{runtime.summary}")
        for step in runtime.steps:
            rprint(f"  - {step.step_key}: {step.status} {step.message}")


@host_app.command("list")
def host_list() -> None:
    """列出主机。"""
    svc = HostService(build_container())
    hosts = svc.list_hosts()
    if not hosts:
        rprint("（暂无主机）")
        return
    for h in hosts:
        rprint(
            f"{h.id}  {h.name}  {h.protocol.value}://{h.address}:{h.port}  os={h.os_type.value}"
        )


@host_app.command("add")
def host_add(
    name: str = typer.Option(...),
    address: str = typer.Option(...),
    protocol: str = typer.Option("ssh", help="ssh|winrm|local"),
    os_type: str = typer.Option("linux", help="linux|windows"),
    port: int | None = typer.Option(None),
    credential_id: str | None = typer.Option(None),
) -> None:
    """新增主机。"""
    svc = HostService(build_container())
    host = svc.upsert_host(
        name=name,
        address=address,
        protocol=protocol,
        os_type=os_type,
        port=port,
        credential_id=credential_id,
    )
    rprint(f"[green]已保存主机[/green] {host.id} {host.name}")


@host_app.command("test")
def host_test(host_id: str = typer.Argument(...)) -> None:
    """测试主机连接。"""
    container = build_container()
    if not container.master_keys.is_unlocked and container.master_keys.is_initialized:
        password = typer.prompt("主密码（远程主机需要）", hide_input=True, default="")
        if password:
            container.master_keys.unlock(password)
    svc = HostService(container)
    msg = svc.test_connection(host_id)
    rprint(f"[green]连接成功：[/green]{msg}")


@host_app.command("delete")
def host_delete(host_id: str = typer.Argument(...)) -> None:
    """删除主机。"""
    HostService(build_container()).delete_host(host_id)
    rprint("[green]已删除[/green]")


@host_app.command("export")
def host_export(path: Path = typer.Argument(...)) -> None:
    """导出主机 CSV。"""
    n = HostService(build_container()).export_csv(path)
    rprint(f"[green]已导出 {n} 台主机到[/green] {path}")


@host_app.command("import")
def host_import(path: Path = typer.Argument(..., exists=True)) -> None:
    """导入主机 CSV。"""
    n = HostService(build_container()).import_csv(path)
    rprint(f"[green]已导入 {n} 台主机[/green]")


@hgroup_app.command("list")
def hgroup_list() -> None:
    """列出主机组。"""
    for g in HostService(build_container()).list_host_groups():
        rprint(f"{g.id}  {g.name}  members={len(g.host_ids)}  {g.remark}")


@hgroup_app.command("add")
def hgroup_add(
    name: str = typer.Option(...),
    host_ids: str = typer.Option(..., help="逗号分隔主机 ID"),
    remark: str = typer.Option(""),
) -> None:
    """创建/更新主机组。"""
    ids = [x.strip() for x in host_ids.split(",") if x.strip()]
    g = HostService(build_container()).upsert_host_group(
        name=name, host_ids=ids, remark=remark
    )
    rprint(f"[green]已保存主机组[/green] {g.id} {g.name} ({len(g.host_ids)} 台)")


@hgroup_app.command("delete")
def hgroup_delete(group_id: str = typer.Argument(...)) -> None:
    """删除主机组。"""
    HostService(build_container()).delete_host_group(group_id)
    rprint("[green]已删除[/green]")


@app.command("logs-cleanup")
def logs_cleanup(retain_days: int = typer.Option(30, help="保留天数")) -> None:
    """清理过期执行日志。"""
    from autoexectool.application.log_cleanup import LogCleanupService

    result = LogCleanupService(build_container()).cleanup(retain_days)
    rprint(f"[green]清理完成[/green] dirs={result['dirs']} files={result['files']}")


@app.command("session-list")
def session_list() -> None:
    """列出最近执行会话。"""
    from autoexectool.application.session_service import SessionService

    for s in SessionService(build_container()).list_sessions(30):
        rprint(f"{s.id}  {s.playbook_name}  {s.status}  {s.trigger}  {s.summary}")


@app.command("session-rerun")
def session_rerun(
    session_id: str = typer.Argument(...),
    from_failed: bool = typer.Option(False, "--from-failed", help="从失败步骤重跑"),
) -> None:
    """重跑历史会话。"""
    from autoexectool.application.session_service import SessionService

    container = build_container()
    new_id = SessionService(container).rerun(session_id, from_failed_step=from_failed)
    runtime = container.orchestrator.get_status(new_id)
    rprint(f"新会话 {new_id} 状态={runtime.status} 摘要={runtime.summary}")


@cred_app.command("list")
def cred_list() -> None:
    """列出凭证（不含明文）。"""
    svc = HostService(build_container())
    rows = svc.list_credentials()
    if not rows:
        rprint("（暂无凭证）")
        return
    for cid, name, auth_type in rows:
        rprint(f"{cid}  {name}  ({auth_type})")


@cred_app.command("add")
def cred_add(
    name: str = typer.Option(...),
    auth_type: str = typer.Option("password", help="password|ssh_key"),
    username: str = typer.Option(""),
    password: str = typer.Option("", hide_input=True, prompt=False),
) -> None:
    """新增加密凭证。"""
    container = build_container()
    setup_logging(container.paths.logs_app)
    if not container.master_keys.is_initialized:
        rprint("[red]请先执行 init-master[/red]")
        raise typer.Exit(1)
    master = typer.prompt("主密码", hide_input=True)
    container.master_keys.unlock(master)
    if auth_type == "password" and not password:
        password = typer.prompt("凭证密码", hide_input=True)
    svc = HostService(container)
    cred = svc.save_credential(
        name=name, auth_type=auth_type, username=username, password=password
    )
    rprint(f"[green]已保存凭证[/green] {cred.id} {cred.name}")


@app.command("group-add")
def group_add(
    name: str = typer.Option(...),
    yaml_file: Path = typer.Option(..., exists=True, help="含 steps 的 YAML 片段文件"),
) -> None:
    """将指令组写入数据库。"""
    import yaml

    container = build_container()
    content = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
    with container.session_factory() as session:
        gid = CommandGroupRepository(session).save(name, content)
    rprint(f"[green]指令组已保存[/green] {name} ({gid})")


@app.command("varset-add")
def varset_add(
    name: str = typer.Option(...),
    yaml_file: Path = typer.Option(..., exists=True, help="变量字典 YAML"),
) -> None:
    """保存变量集。"""
    import yaml

    container = build_container()
    variables = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
    with container.session_factory() as session:
        vid = VariableSetRepository(session).save(name, variables)
    rprint(f"[green]变量集已保存[/green] {name} ({vid})")


@publish_app.command("demo")
def publish_demo() -> None:
    """准备本地演示应用 demo-api。"""
    from autoexectool.publish.service import PublishService

    svc = PublishService(build_container())
    app_id, env_id, package_id = svc.ensure_demo_app()
    rprint(f"[green]演示就绪[/green] app={app_id} env={env_id} package={package_id}")


@publish_app.command("list")
def publish_list() -> None:
    """列出应用与最近发布记录。"""
    from autoexectool.publish.service import PublishService

    svc = PublishService(build_container())
    for a in svc.list_apps():
        rprint(f"应用 {a.id}  {a.name}  deploy={a.deploy_dir}")
        for rec in svc.list_records(a.id)[:5]:
            rprint(f"  - {rec.created_at}  {rec.version}  {rec.status}  {rec.summary}")


@publish_app.command("deploy")
def publish_deploy(
    app_id: str = typer.Option(...),
    env_id: str = typer.Option(...),
    package_id: str = typer.Option(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """执行发布。"""
    from autoexectool.publish.service import PublishService

    result = PublishService(build_container()).deploy(
        app_id=app_id, env_id=env_id, package_id=package_id, dry_run=dry_run
    )
    rprint(result)


@publish_app.command("rollback")
def publish_rollback(
    app_id: str = typer.Option(...),
    env_id: str = typer.Option(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """一键回滚到最近成功发布的备份。"""
    from autoexectool.publish.service import PublishService

    result = PublishService(build_container()).rollback(
        app_id=app_id, env_id=env_id, dry_run=dry_run
    )
    rprint(result)


@app.command("backup")
def backup_cmd() -> None:
    """备份 data 目录为 zip。"""
    from autoexectool.application.backup_service import BackupService

    path = BackupService(build_container()).create_backup()
    rprint(f"[green]备份完成[/green] {path}")


@app.command("plugins")
def plugins_cmd() -> None:
    """列出已加载插件与动作。"""
    container = build_container()
    rprint(f"插件：{container.loaded_plugins or ['（无）']}")
    rprint(f"动作：{container.actions.types()}")


schedule_app = typer.Typer(help="Cron 调度")
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("list")
def schedule_list() -> None:
    container = build_container()
    for row in container.scheduler.list_schedules():
        mode = getattr(row, "mode", None) or "cron"
        when = (
            row.run_at.isoformat()
            if mode == "once" and row.run_at
            else (row.cron or "-")
        )
        rprint(
            f"{row.id}  {row.name}  mode={mode}  when={when}  "
            f"enabled={bool(row.enabled)}  last={row.last_status or '-'}"
        )


@schedule_app.command("add")
def schedule_add(
    name: str = typer.Option(...),
    playbook: Path = typer.Option(..., exists=True),
    cron: str = typer.Option("", help="周期 Cron，如 30 17 * * *；与 --at 二选一"),
    at: str = typer.Option(
        "",
        help="仅一次：本地时间，如 2026-11-23T17:30；与 --cron 二选一",
    ),
) -> None:
    from datetime import datetime

    container = build_container()
    if at.strip():
        run_at = datetime.fromisoformat(at.strip())
        sid = container.scheduler.upsert(
            name=name,
            mode="once",
            run_at=run_at,
            playbook_path=str(playbook),
            enabled=True,
        )
    elif cron.strip():
        sid = container.scheduler.upsert(
            name=name,
            mode="cron",
            cron=cron.strip(),
            playbook_path=str(playbook),
            enabled=True,
        )
    else:
        raise typer.BadParameter("请指定 --at（仅一次）或 --cron（周期）")
    rprint(f"[green]已保存调度[/green] {sid}")


@schedule_app.command("tick")
def schedule_tick() -> None:
    """手动扫描一次到期任务。"""
    fired = build_container().scheduler.tick_once()
    rprint(f"触发 {len(fired)} 个：{fired}")


@app.command("gui")
def gui_cmd() -> None:
    """启动桌面界面。"""
    from autoexectool.app.main import run_gui

    run_gui()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
