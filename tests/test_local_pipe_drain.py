from __future__ import annotations

import sys

from autoexectool.connectors.local import LocalConnector
from autoexectool.domain.enums import OsType, ProtocolType
from autoexectool.domain.models import Host


def test_large_stdout_does_not_deadlock() -> None:
    """大量 stdout 不得堵死管道（旧实现会卡到超时）。"""
    host = Host(
        id="l",
        name="local",
        address="127.0.0.1",
        port=0,
        os_type=OsType.WINDOWS,
        protocol=ProtocolType.LOCAL,
    )
    conn = LocalConnector()
    session = conn.connect(host, None)
    # 约数 MB 输出，远超常见管道缓冲
    py = sys.executable
    cmd = (
        f'"{py}" -c "import sys; '
        f"[sys.stdout.write('x'*1024) for _ in range(3000)]; "
        f'sys.stdout.flush()"'
    )
    result = conn.exec(session, cmd, timeout=30)
    assert result.exit_code == 0
    assert len(result.stdout) >= 3000 * 1024
