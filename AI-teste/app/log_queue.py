import threading
from collections import deque
from datetime import datetime


class LogQueue:
    """Thread-safe log entry queue. Background threads push; JS polls drain()."""

    def __init__(self):
        self._q: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def push(self, level: str, message: str):
        """
        Push a log entry. Call from any thread.
        Levels: info | success | warn | error | scilab | code
        """
        entry = {
            "level": level,
            "message": message,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        with self._lock:
            self._q.append(entry)

    def drain(self) -> list:
        """Return and clear all pending entries. Called from pywebview JS poll."""
        with self._lock:
            entries = list(self._q)
            self._q.clear()
            return entries
