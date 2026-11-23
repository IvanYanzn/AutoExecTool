from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from autoexectool.actions.registry import ActionRegistry, default_action_registry
from autoexectool.connectors.registry import ConnectorRegistry, default_connector_registry
from autoexectool.orchestrator.engine import Orchestrator
from autoexectool.orchestrator.session_store import SessionStore
from autoexectool.plugin.loader import ExtensionRegistry, load_plugins
from autoexectool.scheduler.service import SchedulerService
from autoexectool.security.crypto import CredentialVault, MasterKeyManager
from autoexectool.storage.db import create_engine_for_paths, init_db, make_session_factory
from autoexectool.storage.paths import DataPaths, resolve_data_paths
from autoexectool.logging.setup import get_logger


@dataclass
class AppContainer:
    paths: DataPaths
    engine: Engine
    session_factory: sessionmaker[Session]
    master_keys: MasterKeyManager
    vault: CredentialVault
    connectors: ConnectorRegistry
    actions: ActionRegistry
    orchestrator: Orchestrator
    scheduler: SchedulerService | None
    loaded_plugins: list[str] = field(default_factory=list)


def build_container(data_root=None) -> AppContainer:
    paths = resolve_data_paths(data_root)
    engine = create_engine_for_paths(paths)
    init_db(engine)
    session_factory = make_session_factory(engine)
    master = MasterKeyManager(paths.keys)
    vault = CredentialVault(master)
    connectors = default_connector_registry()
    actions = default_action_registry()

    from autoexectool.runtime_paths import plugins_dir

    ext = ExtensionRegistry(actions=actions, connectors=connectors)
    loaded = load_plugins(plugins_dir(), ext)

    def resolve_group(name: str) -> dict:
        from autoexectool.storage.repositories import CommandGroupRepository

        with session_factory() as session:
            return CommandGroupRepository(session).get_content(name)

    session_store = SessionStore(session_factory)
    interrupted = session_store.mark_interrupted_running()
    if interrupted:
        get_logger("app").warning("marked %s sessions as Interrupted", interrupted)

    # 先占位，注入 resolve_host 时再绑到完整 container
    orchestrator = Orchestrator(
        actions=actions,
        connectors=connectors,
        data_paths=paths,
        resolve_group=resolve_group,
        resolve_host=None,
        lock_hosts=True,
        session_store=session_store,
    )
    container = AppContainer(
        paths=paths,
        engine=engine,
        session_factory=session_factory,
        master_keys=master,
        vault=vault,
        connectors=connectors,
        actions=actions,
        orchestrator=orchestrator,
        scheduler=None,
        loaded_plugins=loaded,
    )

    from autoexectool.application.host_service import HostService

    host_svc = HostService(container)
    orchestrator.resolve_host = host_svc.resolve_by_ref

    container.scheduler = SchedulerService(container)
    return container

