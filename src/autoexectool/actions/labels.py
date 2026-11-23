from __future__ import annotations

# 动作 code → 中文名称（含别名）
ACTION_LABELS: dict[str, str] = {
    "shell.exec": "Shell 命令",
    "shell": "Shell 命令",
    "powershell.exec": "PowerShell 命令",
    "powershell": "PowerShell 命令",
    "cmd.exec": "CMD 命令",
    "cmd": "CMD 命令",
    "delay": "延时等待",
    "wait.until": "等到指定时间",
    "file.upload": "上传文件",
    "file.download": "下载文件",
    "script.upload_and_run": "上传并执行脚本",
    "process.wait": "等待进程",
    "condition": "条件判断",
    "fs.copy_tree": "目录复制",
    "http.healthcheck": "HTTP 健康检查",
    "notify": "Webhook 通知",
    "service.control": "服务控制",
    "sample.echo": "示例回显（插件）",
}

# 连接协议
PROTOCOL_LABELS: dict[str, str] = {
    "local": "本机",
    "ssh": "SSH（Linux/Unix）",
    "winrm": "WinRM（Windows）",
}


def action_label(code: str) -> str:
    return ACTION_LABELS.get(code, code)


def protocol_label(code: str) -> str:
    return PROTOCOL_LABELS.get(code, code)


def format_action(code: str, name: str | None = None) -> str:
    n = name or action_label(code)
    if n == code:
        return code
    return f"{n}（{code}）"
