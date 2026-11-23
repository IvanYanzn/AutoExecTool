from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from autoexectool.domain.errors import AppError, ErrorCode


class HostLockManager:
    """同一主机变更类流程互斥（完整版必达）。"""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _get(self, host_id: str) -> threading.Lock:
        with self._guard:
            if host_id not in self._locks:
                self._locks[host_id] = threading.Lock()
            return self._locks[host_id]

    @contextmanager
    def acquire(self, host_id: str, *, blocking: bool = False) -> Iterator[None]:
        with self.acquire_many([host_id], blocking=blocking):
            yield

    @contextmanager
    def acquire_many(
        self, host_ids: list[str], *, blocking: bool = False
    ) -> Iterator[None]:
        """按 id 排序加锁，避免多主机并行时死锁。"""
        ordered = sorted({h for h in host_ids if h})
        acquired: list[threading.Lock] = []
        try:
            for host_id in ordered:
                lock = self._get(host_id)
                got = lock.acquire(
                    blocking=blocking, timeout=0 if not blocking else None
                )
                if not got:
                    raise AppError(
                        ErrorCode.VALIDATION_ERROR,
                        "该主机已有变更类任务在执行，请稍后重试。",
                        detail=f"host_id={host_id}",
                    )
                acquired.append(lock)
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()


GLOBAL_HOST_LOCKS = HostLockManager()
