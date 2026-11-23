from __future__ import annotations

import platform
import time
from pathlib import Path
from typing import Any

import httpx

from autoexectool.actions.base import ExecutionContext
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.domain.models import ActionResult


def _require(params: dict[str, Any], key: str) -> Any:
    if key not in params or params[key] in (None, ""):
        raise AppError(ErrorCode.VALIDATION_ERROR, f"缺少参数：{key}")
    return params[key]


def _connector_exec(
    ctx: ExecutionContext, command: str, timeout: float | None = None
):
    """调用连接器执行；透传 cancel，便于中止阻塞中的本地进程。"""
    return ctx.connector.exec(
        ctx.session, command, timeout=timeout, cancel=ctx.cancel
    )


class ShellExecAction:
    type = "shell.exec"
    os = "any"  # 本地 Windows 亦可经 cmd/shell 执行；远程 Linux 为主场景

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "command")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        command = str(params["command"])
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] shell.exec: {command}")
        started = time.perf_counter()
        result = _connector_exec(ctx, command, timeout=params.get("timeout"))
        duration = int((time.perf_counter() - started) * 1000)
        return ActionResult(
            success=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            message="命令执行完成" if result.exit_code == 0 else "命令失败",
            duration_ms=duration,
        )


class PowerShellExecAction:
    type = "powershell.exec"
    os = "windows"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "command")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        command = str(params["command"])
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] powershell.exec: {command}")
        # Local on Windows: wrap; WinRM connector already runs PS
        if ctx.host.protocol.value == "local" and platform.system() == "Windows":
            wrapped = f'powershell -NoProfile -Command "{command.replace(chr(34), chr(92)+chr(34))}"'
            result = _connector_exec(ctx, wrapped, timeout=params.get("timeout"))
        else:
            result = _connector_exec(ctx, command, timeout=params.get("timeout"))
        return ActionResult(
            success=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            message="PowerShell 执行完成" if result.exit_code == 0 else "PowerShell 失败",
        )


class CmdExecAction:
    type = "cmd.exec"
    os = "windows"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "command")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        command = str(params["command"])
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] cmd.exec: {command}")
        result = _connector_exec(ctx, command, timeout=params.get("timeout"))
        return ActionResult(
            success=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            message="cmd 执行完成" if result.exit_code == 0 else "cmd 失败",
        )


class DelayAction:
    type = "delay"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        sec = params.get("seconds", params.get("sec"))
        if sec is None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "delay 需要 seconds")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        seconds = float(params.get("seconds", params.get("sec", 0)))
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] delay {seconds}s")
        time.sleep(max(0.0, seconds))
        return ActionResult(success=True, message=f"已等待 {seconds} 秒")


class WaitUntilAction:
    type = "wait.until"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        if "execute_at" not in params and "at" not in params:
            raise AppError(ErrorCode.VALIDATION_ERROR, "wait.until 需要 execute_at")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        # 实际等待由编排引擎统一处理 schedule；此处兼容独立动作
        return ActionResult(success=True, message="wait.until 由编排引擎调度")


class FileUploadAction:
    type = "file.upload"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "local")
        _require(params, "remote")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        local = Path(str(params["local"]))
        remote = str(params["remote"])
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] upload {local} -> {remote}")
        if not local.exists():
            raise AppError(ErrorCode.VALIDATION_ERROR, f"本地文件不存在：{local}")
        ctx.connector.upload(ctx.session, local, remote)
        return ActionResult(success=True, message=f"已上传到 {remote}")


class FileDownloadAction:
    type = "file.download"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "remote")
        _require(params, "local")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        remote = str(params["remote"])
        local = Path(str(params["local"]))
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] download {remote} -> {local}")
        ctx.connector.download(ctx.session, remote, local)
        return ActionResult(success=True, message=f"已下载到 {local}")


class ScriptUploadAndRunAction:
    type = "script.upload_and_run"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "local")
        _require(params, "remote")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        local = Path(str(params["local"]))
        remote = str(params["remote"])
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] upload_and_run {local}")
        if not local.exists():
            raise AppError(ErrorCode.VALIDATION_ERROR, f"脚本不存在：{local}")
        ctx.connector.upload(ctx.session, local, remote)
        if ctx.host.os_type.value == "windows":
            cmd = str(params.get("command") or f'powershell -NoProfile -File "{remote}"')
        else:
            cmd = str(params.get("command") or f"chmod +x '{remote}' && '{remote}'")
        result = ctx.connector.exec(ctx.session, cmd, timeout=params.get("timeout"))
        return ActionResult(
            success=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            message="脚本执行完成" if result.exit_code == 0 else "脚本执行失败",
        )


class ProcessWaitAction:
    type = "process.wait"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "name")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        name = str(params["name"])
        appear = bool(params.get("appear", True))
        retries = int(params.get("retries", 10))
        interval = float(params.get("interval_sec", 2))
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] process.wait {name}")
        for _ in range(max(1, retries)):
            if ctx.host.os_type.value == "windows":
                cmd = f'Get-Process -Name "{name}" -ErrorAction SilentlyContinue | Select-Object -First 1'
            else:
                cmd = f"pgrep -f '{name}' >/dev/null"
            result = ctx.connector.exec(ctx.session, cmd)
            if ctx.host.os_type.value == "windows":
                exists = result.exit_code == 0 and bool((result.stdout or "").strip())
            else:
                exists = result.exit_code == 0
            if appear and exists:
                return ActionResult(success=True, message=f"进程已出现：{name}")
            if not appear and not exists:
                return ActionResult(success=True, message=f"进程已退出：{name}")
            time.sleep(interval)
        return ActionResult(success=False, message=f"等待进程超时：{name}")


class ConditionAction:
    type = "condition"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "expression")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        expr = str(params["expression"]).strip()
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] condition {expr}")
        # 仅支持简单：var==value / var!=value / 真值变量名
        try:
            if "==" in expr:
                left, right = [x.strip() for x in expr.split("==", 1)]
                ok = str(ctx.variables.get(left, "")) == right.strip("'\"")
            elif "!=" in expr:
                left, right = [x.strip() for x in expr.split("!=", 1)]
                ok = str(ctx.variables.get(left, "")) != right.strip("'\"")
            else:
                ok = bool(ctx.variables.get(expr))
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCode.VALIDATION_ERROR, f"条件解析失败：{expr}") from exc
        if not ok:
            return ActionResult(success=False, message=f"条件不成立：{expr}")
        return ActionResult(success=True, message=f"条件成立：{expr}", outputs={"condition": True})


class HttpHealthcheckAction:
    type = "http.healthcheck"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "url")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        url = str(params["url"])
        expect = int(params.get("expect_status", 200))
        retries = int(params.get("retries", 1))
        interval = float(params.get("interval_sec", 2))
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] healthcheck {url}")
        last_err = ""
        for _ in range(max(1, retries)):
            try:
                resp = httpx.get(url, timeout=10.0)
                if resp.status_code == expect:
                    return ActionResult(
                        success=True,
                        exit_code=0,
                        message=f"健康检查通过：HTTP {resp.status_code}",
                        outputs={"status_code": resp.status_code},
                    )
                last_err = f"HTTP {resp.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
            time.sleep(interval)
        return ActionResult(success=False, message=f"健康检查失败：{last_err}")


class FsCopyTreeAction:
    """复制目录树（发布备份/部署常用）。Local 用 shutil；远程用系统命令。"""

    type = "fs.copy_tree"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "src")
        _require(params, "dest")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        import shutil

        src = str(params["src"])
        dest = str(params["dest"])
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] copy_tree {src} -> {dest}")
        if ctx.host.protocol.value == "local":
            src_p, dest_p = Path(src), Path(dest)
            if not src_p.exists():
                # 首次发布无旧目录时允许跳过备份源
                if params.get("ok_if_missing"):
                    return ActionResult(success=True, message=f"源不存在，已跳过：{src}")
                raise AppError(ErrorCode.VALIDATION_ERROR, f"源目录不存在：{src}")
            if dest_p.exists():
                shutil.rmtree(dest_p)
            dest_p.parent.mkdir(parents=True, exist_ok=True)
            if src_p.is_file():
                dest_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_p, dest_p)
            else:
                shutil.copytree(src_p, dest_p)
            return ActionResult(success=True, message=f"已复制到 {dest}")
        # 远程：按 OS 下发命令
        if ctx.host.os_type.value == "windows":
            cmd = (
                f"if (Test-Path '{src}') {{ "
                f"New-Item -ItemType Directory -Force -Path (Split-Path '{dest}') | Out-Null; "
                f"Copy-Item -Recurse -Force '{src}' '{dest}' }} "
                f"elseif ({str(bool(params.get('ok_if_missing'))).lower()}) {{ }} "
                f"else {{ throw 'src missing' }}"
            )
        else:
            ok = "true" if params.get("ok_if_missing") else "false"
            cmd = (
                f"if [ -e '{src}' ]; then mkdir -p \"$(dirname '{dest}')\" && "
                f"rm -rf '{dest}' && cp -a '{src}' '{dest}'; "
                f"elif [ '{ok}' = true ]; then true; else echo missing; exit 1; fi"
            )
        result = ctx.connector.exec(ctx.session, cmd)
        return ActionResult(
            success=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            message="目录复制完成" if result.exit_code == 0 else "目录复制失败",
        )


class NotifyAction:
    """Webhook 通知（完整版必达）。"""

    type = "notify"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "url")
        _require(params, "message")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        url = str(params["url"])
        message = str(params["message"])
        payload = params.get("payload")
        if payload is None:
            payload = {"text": message, "message": message}
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] notify {url}")
        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
            ok = 200 <= resp.status_code < 300
            return ActionResult(
                success=ok,
                exit_code=0 if ok else resp.status_code,
                message=f"通知已发送 HTTP {resp.status_code}" if ok else f"通知失败 HTTP {resp.status_code}",
                stdout=resp.text[:1000],
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(success=False, message=f"通知异常：{exc}")


class ServiceControlAction:
    type = "service.control"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        _require(params, "service")
        _require(params, "operation")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        service = str(params["service"])
        operation = str(params["operation"]).lower()
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] service {operation} {service}")
        if ctx.host.os_type.value == "windows":
            mapping = {
                "start": f"Start-Service -Name '{service}'",
                "stop": f"Stop-Service -Name '{service}' -Force",
                "restart": f"Restart-Service -Name '{service}' -Force",
                "status": f"Get-Service -Name '{service}' | Format-List",
            }
            cmd = mapping.get(operation)
            if not cmd:
                raise AppError(ErrorCode.VALIDATION_ERROR, f"不支持的 operation：{operation}")
            # 复用 powershell 语义
            if ctx.host.protocol.value == "local":
                wrapped = f'powershell -NoProfile -Command "{cmd}"'
                result = ctx.connector.exec(ctx.session, wrapped)
            else:
                result = ctx.connector.exec(ctx.session, cmd)
        else:
            mapping = {
                "start": f"systemctl start {service}",
                "stop": f"systemctl stop {service}",
                "restart": f"systemctl restart {service}",
                "status": f"systemctl status {service} --no-pager",
            }
            cmd = mapping.get(operation)
            if not cmd:
                raise AppError(ErrorCode.VALIDATION_ERROR, f"不支持的 operation：{operation}")
            result = ctx.connector.exec(ctx.session, cmd)
        return ActionResult(
            success=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            message=f"服务 {operation} 完成" if result.exit_code == 0 else f"服务 {operation} 失败",
        )
