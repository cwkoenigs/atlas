"""One reentrant thread/process lock per inventory and durable atomic file replacement."""
from contextlib import contextmanager
import fcntl
import os
import pathlib
import tempfile
import threading

_registry = {}
_registry_lock = threading.Lock()


@contextmanager
def locked(root):
    root = pathlib.Path(root).resolve()
    with _registry_lock:
        mutex, local = _registry.setdefault(root, (threading.RLock(), threading.local()))
    with mutex:
        depth = getattr(local, 'depth', 0)
        if not depth:
            directory = root / '.state'
            directory.mkdir(parents=True, exist_ok=True)
            local.file = (directory / 'write.lock').open('a')
            try:
                fcntl.flock(local.file.fileno(), fcntl.LOCK_EX)
            except BaseException:
                local.file.close()
                raise
        local.depth = depth + 1
        try:
            yield
        finally:
            local.depth -= 1
            if not local.depth:
                fcntl.flock(local.file.fileno(), fcntl.LOCK_UN)
                local.file.close()


def atomic_write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            if path.exists():
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_text(path):
    """Capture the on-disk text without normalizing an external editor's line endings."""
    with pathlib.Path(path).open("r", encoding="utf-8", newline="") as stream:
        return stream.read()
