"""Changing a file in the platforms repository.

The mutating half of the read side in :mod:`platform_repo`, kept separate
because the rules are different: every function here is guarded, every one is
serialized behind one lock, and every one leaves the tree in a state a human
could have produced by hand.

ONE LOCK FOR THE WHOLE MODULE. zenoh dispatches each queryable callback on its
own thread, so two saves can arrive at once, and a git index is not safe to
share. The lock is module-level rather than per-instance because the thing being
protected is the working tree on disk, not a Python object -- two responder
instances in one process pointed at one checkout would still be one tree.

WRITES ARE ATOMIC. A temporary file in the same directory, then ``os.replace``,
which is atomic on POSIX within a filesystem. A half-written compose file is
worse than an unwritten one: it may still parse, and it will be deployed.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from .platform_repo import RepoError, sha256_of

logger = logging.getLogger("keelson-interface-docker.platform")

#: Serializes every mutation of the working tree. See the module docstring.
TREE_LOCK = threading.RLock()


def check_base_sha(path: Path, base_sha256: str) -> bytes:
    """Verify the caller edited the version that is still on disk.

    Returns the current bytes so a caller need not read twice.

    THE EMPTY STRING MEANS "I EXPECT THIS FILE NOT TO EXIST" -- the create case.
    It deliberately does NOT mean "I do not care": a blind overwrite of a change
    someone else made is precisely the failure this check exists to prevent, and
    an escape hatch would be used on the day it mattered.

    A mismatch is INVALID_STATE rather than an error to retry -- the caller must
    re-read and re-apply, which a client renders as "the file changed on disk,
    reload and re-apply your edit?" rather than a red banner.
    """
    exists = path.is_file()

    if not base_sha256:
        if exists:
            raise RepoError(
                ErrorResponse.Code.INVALID_STATE,
                "this file already exists; read it and pass its sha256 "
                "as base_sha256 to replace it",
            )
        return b""

    if not exists:
        raise RepoError(
            ErrorResponse.Code.INVALID_STATE,
            "the file no longer exists; it was deleted after you read it",
        )

    current = path.read_bytes()
    actual = sha256_of(current)
    if actual != base_sha256:
        raise RepoError(
            ErrorResponse.Code.INVALID_STATE,
            (
                "the file changed on disk since you read it "
                f"(expected {base_sha256[:12]}, found {actual[:12]}); "
                "re-read it and re-apply your edit"
            ),
        )
    return current


def atomic_write(path: Path, content: bytes) -> None:
    """Replace *path*'s contents in one step, preserving its mode if it exists.

    The temporary file is created in the SAME directory, because ``os.replace``
    is only atomic within a filesystem and ``/tmp`` is frequently a different
    one. It is also why the temp file cannot simply be left to ``tempfile``'s
    default location.
    """
    parent = path.parent
    if not parent.is_dir():
        raise RepoError(
            ErrorResponse.Code.NOT_FOUND,
            (
                f"no such directory: {parent.name}/ -- this interface edits an "
                "entity's configuration, it does not create entities"
            ),
        )

    mode = path.stat().st_mode & 0o777 if path.is_file() else 0o644

    fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            # The rename is atomic, but the CONTENT still has to be on disk for
            # that to mean anything after a power loss.
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise RepoError(ErrorResponse.Code.IO_FAILURE, f"could not write: {exc}") from exc
