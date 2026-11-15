"""Thread-safe pause flag shared across the pipeline and UI."""

import threading

_lock = threading.Lock()
_paused = False


def set_paused(value: bool):
    global _paused
    with _lock:
        _paused = value


def toggle_paused() -> bool:
    global _paused
    with _lock:
        _paused = not _paused
        return _paused


def is_paused() -> bool:
    with _lock:
        return _paused
