"""Local candidate I/O, not production state or a cross-system transaction.

Stable flock files are never unlinked: stale files do not imply live locks, and
process exit releases the kernel lock without racing another lock-file inode.
Files become visible only after a complete, flushed temporary file exists.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BlockingIOError('Another candidate worker holds ' + str(path)) from exc
        yield
    finally:
        os.close(fd)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(path, body, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', suffix='.pending', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            # Same filesystem; link is exclusive and never replaces an existing ZIP.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_json(path, value, *, immutable=False):
    body = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(',', ':')) + '\n').encode()
    atomic_bytes(path, body, immutable=immutable)


def candidate_destination(source, destination):
    """No candidate output can overlap its baseline or repository data/public."""
    from .common import ROOT
    source, destination = Path(source).resolve(), Path(destination).absolute()
    resolved = destination.resolve()
    for protected in (source, ROOT / 'data', ROOT / 'frontend/public'):
        protected = protected.resolve()
        if resolved == protected or protected in resolved.parents or resolved in protected.parents:
            raise ValueError('Candidate output overlaps protected input: ' + str(destination))
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Candidate output is immutable; choose a new run/attempt path')
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def publish_directory(staged, destination):
    """Caller holds destination lock; publish a complete directory on one filesystem.

    Atomic visibility, not a claim of power-loss durability for every contained
    file. Stage 4C-2 must provide its own durable production storage contract.
    """
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Candidate output already exists')
    os.rename(staged, destination)
