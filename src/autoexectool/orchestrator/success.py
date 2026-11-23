from __future__ import annotations

from typing import Any

from autoexectool.domain.models import ActionResult


def evaluate_success(result: ActionResult, success_when: dict[str, Any] | None) -> bool:
    """按成功条件判定；未配置时默认 exit_code==0 或 result.success。"""
    if not success_when:
        return bool(result.success)
    if "exit_codes" in success_when:
        codes = success_when["exit_codes"]
        if result.exit_code not in list(codes):
            return False
    elif "exit_code" in success_when:
        if result.exit_code != int(success_when["exit_code"]):
            return False
    if "stdout_contains" in success_when:
        needle = str(success_when["stdout_contains"])
        if needle not in (result.stdout or ""):
            return False
    if "stdout_not_contains" in success_when:
        needle = str(success_when["stdout_not_contains"])
        if needle in (result.stdout or ""):
            return False
    if "stderr_contains" in success_when:
        needle = str(success_when["stderr_contains"])
        if needle not in (result.stderr or ""):
            return False
    return True
