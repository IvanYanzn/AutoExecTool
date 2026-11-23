"""示例外部插件：注册 sample.echo 动作。"""

from __future__ import annotations

from typing import Any

from autoexectool.actions.base import ExecutionContext
from autoexectool.domain.models import ActionResult


class SampleEchoAction:
    type = "sample.echo"
    display_name = "示例回显（插件）"
    os = "any"

    def validate(self, params: dict[str, Any]) -> None:
        if "text" not in params:
            raise ValueError("sample.echo 需要 text")

    def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> ActionResult:
        text = str(params.get("text", ""))
        if ctx.dry_run:
            return ActionResult(success=True, message=f"[dry-run] echo {text}")
        return ActionResult(success=True, message=text, stdout=text)


def register(registry) -> None:
    registry.actions.register(SampleEchoAction())
