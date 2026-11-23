from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    HOST_UNREACHABLE = "HOST_UNREACHABLE"
    AUTH_FAILED = "AUTH_FAILED"
    PROTOCOL_UNSUPPORTED = "PROTOCOL_UNSUPPORTED"
    STEP_TIMEOUT = "STEP_TIMEOUT"
    STEP_FAILED = "STEP_FAILED"
    SCHEDULE_EXPIRED = "SCHEDULE_EXPIRED"
    SCHEDULE_WAIT_TIMEOUT = "SCHEDULE_WAIT_TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    PLUGIN_LOAD_ERROR = "PLUGIN_LOAD_ERROR"
    CRYPTO_ERROR = "CRYPTO_ERROR"
    NOT_INITIALIZED = "NOT_INITIALIZED"


ERROR_MESSAGES_ZH: dict[ErrorCode, str] = {
    ErrorCode.HOST_UNREACHABLE: "主机网络不可达，请检查地址、端口与网络。",
    ErrorCode.AUTH_FAILED: "认证失败，请检查用户名、密码或密钥。",
    ErrorCode.PROTOCOL_UNSUPPORTED: "协议或动作与目标操作系统不匹配。",
    ErrorCode.STEP_TIMEOUT: "步骤执行超时。",
    ErrorCode.STEP_FAILED: "步骤命令执行失败。",
    ErrorCode.SCHEDULE_EXPIRED: "计划执行时间已过，且策略为失败。",
    ErrorCode.SCHEDULE_WAIT_TIMEOUT: "等待计划执行时间超过上限。",
    ErrorCode.CANCELLED: "任务已被取消。",
    ErrorCode.INTERRUPTED: "进程异常中断，会话未正常结束。",
    ErrorCode.VALIDATION_ERROR: "参数或流程定义校验失败。",
    ErrorCode.STORAGE_ERROR: "数据库或文件读写失败。",
    ErrorCode.PLUGIN_LOAD_ERROR: "插件加载失败。",
    ErrorCode.CRYPTO_ERROR: "加解密失败，请确认主密码是否正确。",
    ErrorCode.NOT_INITIALIZED: "应用尚未完成初始化（如主密码未设置）。",
}


class AppError(Exception):
    """带稳定错误码的领域异常。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        detail: str | None = None,
    ) -> None:
        self.code = code
        self.message = message or ERROR_MESSAGES_ZH.get(code, str(code))
        self.detail = detail
        super().__init__(self.message)

    def to_user_text(self) -> str:
        if self.detail:
            return f"[{self.code}] {self.message}\n详情：{self.detail}"
        return f"[{self.code}] {self.message}"
