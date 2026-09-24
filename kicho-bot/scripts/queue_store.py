"""Serialize local queue access on WSL/Linux and macOS."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path


@contextmanager
def queue_lock(path: Path):
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
