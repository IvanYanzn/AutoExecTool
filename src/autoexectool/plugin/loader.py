from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from autoexectool.actions.registry import ActionRegistry
from autoexectool.connectors.registry import ConnectorRegistry
from autoexectool.domain.errors import AppError, ErrorCode
from autoexectool.logging.setup import get_logger

logger = get_logger("plugin")


class ExtensionRegistry:
    def __init__(self, actions: ActionRegistry, connectors: ConnectorRegistry) -> None:
        self.actions = actions
        self.connectors = connectors
        self.loaded: list[str] = []


def load_plugins(plugins_dir: Path, registry: ExtensionRegistry) -> list[str]:
    """扫描 plugins/<id>/plugin.json 并加载；单插件失败不影响内核。"""
    loaded: list[str] = []
    if not plugins_dir.exists():
        return loaded
    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / "plugin.json"
        if not manifest.exists():
            continue
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
            plugin_id = str(meta.get("id") or child.name)
            entry = str(meta.get("entry") or "plugin:register")
            module_file, func_name = _parse_entry(entry, child)
            mod = _load_module(plugin_id, module_file)
            register = getattr(mod, func_name, None)
            if not callable(register):
                raise AppError(
                    ErrorCode.PLUGIN_LOAD_ERROR,
                    f"插件入口不可调用：{entry}",
                )
            register(registry)
            loaded.append(plugin_id)
            registry.loaded.append(plugin_id)
            logger.info("loaded plugin %s", plugin_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("plugin load failed: %s (%s)", child.name, exc)
    return loaded


def _parse_entry(entry: str, plugin_dir: Path) -> tuple[Path, str]:
    # "plugin:register" -> plugin.py / register
    if ":" in entry:
        mod_name, func_name = entry.split(":", 1)
    else:
        mod_name, func_name = entry, "register"
    path = plugin_dir / f"{mod_name}.py"
    if not path.exists():
        raise AppError(ErrorCode.PLUGIN_LOAD_ERROR, f"插件模块不存在：{path}")
    return path, func_name


def _load_module(plugin_id: str, path: Path) -> Any:
    mod_name = f"autoexectool_plugins_{plugin_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise AppError(ErrorCode.PLUGIN_LOAD_ERROR, f"无法加载：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module
