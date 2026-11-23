from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def render_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            # 支持 host.address 这类嵌套：先扁平查找，再点分查找
            if key in variables:
                return str(variables[key])
            cur: Any = variables
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return match.group(0)
            return str(cur)

        return _PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [render_value(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: render_value(v, variables) for k, v in value.items()}
    return value


def render_params(params: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    return {k: render_value(v, variables) for k, v in params.items()}
