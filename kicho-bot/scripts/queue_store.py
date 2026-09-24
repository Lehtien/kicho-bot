"""Serialize local queue access on Windows, Linux and macOS."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def acquire(descriptor: int) -> None:
    if os.name != "nt":
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return
    # Lock the same byte, including in a newly created empty lock file.
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            time.sleep(0.05)


def release(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def queue_lock(path: Path):
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "r+b") as lock:
        acquire(lock.fileno())
        try:
            yield
        finally:
            release(lock.fileno())
