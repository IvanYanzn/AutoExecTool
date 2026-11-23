from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"(password\s*[=:]\s*)([^\s\"']+)", re.I),
    re.compile(r"(passwd\s*[=:]\s*)([^\s\"']+)", re.I),
    re.compile(r"(token\s*[=:]\s*)([^\s\"']+)", re.I),
    re.compile(r"(secret\s*[=:]\s*)([^\s\"']+)", re.I),
    re.compile(r"(Authorization:\s*Bearer\s+)(\S+)", re.I),
]


def mask_secrets(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(r"\1******", out)
    return out
