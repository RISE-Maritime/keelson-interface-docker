"""Container healthcheck probe.

``app.py`` pings the Docker socket once at startup and exits if it cannot be
reached. That covers a container that never worked; it does not cover a socket
that goes away *afterwards* -- a daemon restart, a changed docker gid, a
revoked mount. In that state the process keeps serving, every RPC returns
UNAVAILABLE, and the container still reports healthy. This probe is what makes
that visible from outside.

Imports ONLY :mod:`.backend` -- never ``.app`` or ``.cli`` -- so a probe every
30 seconds does not pay to import zenoh and argparse. And it calls the very
same :meth:`DockerBackend.ping` the startup gate calls, so the two can never
disagree about what "reachable" means.

Note this is VISIBILITY, not recovery: ``restart: unless-stopped`` reacts to a
container *exiting*, not to it going unhealthy. Nothing here auto-heals.
"""

from __future__ import annotations

import sys

from .backend import BackendError, DockerBackend

#: Client-side budget for the probe. Must stay below the HEALTHCHECK --timeout
#: in the Dockerfile, so a hung daemon produces a readable message here rather
#: than an unexplained SIGKILL with empty Health.Log[].Output.
PING_TIMEOUT_S = 5


def main() -> int:
    try:
        DockerBackend(timeout=PING_TIMEOUT_S).ping()
    except BackendError as exc:
        # Goes to `docker inspect --format '{{json .State.Health}}'`, which is
        # the only place anyone will read it.
        print(exc.message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
