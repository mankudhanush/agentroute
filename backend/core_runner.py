"""Runs router.route() on one thread.

RoutingMemory uses a SQLite connection, which must stay on the thread that
opened it. The HTTP handlers stay free to answer health checks.
"""

import threading
from concurrent.futures import Future
from queue import Queue


class RouteExecutor:
    def __init__(self, memory_factory):
        self._factory = memory_factory
        self._queue: Queue = Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="agentroute-core", daemon=True)
        self._thread.start()
        self._ready.wait()

    def _loop(self) -> None:
        memory = self._factory()
        self._ready.set()
        while True:
            item = self._queue.get()
            if item is None:
                close = getattr(memory, "close", None)
                if close is not None:
                    close()
                return
            fn, future = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(memory))
            except Exception as exc:
                future.set_exception(exc)

    def submit(self, fn):
        future: Future = Future()
        self._queue.put((fn, future))
        return future

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)
