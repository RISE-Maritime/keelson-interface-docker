"""Who is allowed to start, stop or restart what.

Mounting the Docker socket makes this process root-equivalent on its host:
anything that can reach the Engine API through it can start a privileged
container with ``/`` bind-mounted. The previous version of this interface
exposed that to any peer that could reach one zenoh key, with no check of any
kind. This module is the check.

Pure -- imports neither ``docker`` nor ``zenoh`` -- so the policy is testable
without a daemon or a bus.
"""

from __future__ import annotations

from dataclasses import dataclass

from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from .model import matches_any


@dataclass(frozen=True)
class Decision:
    """The answer to "may I mutate this container?".

    ``reason`` names *which* guard fired, because the operator's next action
    differs: turn the responder's control on, widen its allow-list, or stop
    trying to restart the thing that would answer them.
    """

    allowed: bool
    reason: str = ""
    code: int = ErrorResponse.Code.PERMISSION_DENIED


ALLOWED = Decision(allowed=True)


@dataclass(frozen=True)
class ControlGuard:
    """Read-only unless told otherwise, then only for named containers."""

    #: False (the default) makes every mutating procedure reply PERMISSION_DENIED.
    control_enabled: bool = False
    #: fnmatch globs against the container NAME. Never empty when control is on:
    #: ``app.py`` rejects that combination at startup rather than presenting a
    #: responder that looks enabled and refuses everything.
    allow_globs: tuple[str, ...] = ()
    #: Every resolved spelling of this responder's own container -- explicit
    #: name, full id, short id. See :mod:`selfid`.
    self_identity: frozenset[str] = frozenset()

    def decide(self, name: str, container_id: str = "", verb: str = "control") -> Decision:
        """Whether ``verb`` may be performed on the named container.

        Evaluated *before* the container is looked up, so a denied call cannot
        be used to probe whether a given container exists on the host.
        """
        if not self.control_enabled:
            return Decision(
                allowed=False,
                reason=(
                    "container control is disabled on this responder "
                    "(start it with --allow-control)"
                ),
            )

        if self.is_self(name, container_id):
            return Decision(
                allowed=False,
                reason=(
                    f"refusing to {verb} {name!r}: that is this responder's own "
                    "container, and stopping it would kill this call mid-flight"
                ),
            )

        if not matches_any(name, self.allow_globs):
            allowed = ", ".join(self.allow_globs) or "<none>"
            return Decision(
                allowed=False,
                reason=(f"{name!r} is not in this responder's control allow-list ({allowed})"),
            )

        return ALLOWED

    def is_self(self, name: str, container_id: str = "") -> bool:
        if name and name in self.self_identity:
            return True
        if container_id and container_id in self.self_identity:
            return True
        # Callers see the full 64-hex id; --self-container-name may have been
        # resolved from a short id, or vice versa.
        return bool(container_id) and any(
            len(known) >= 12 and (container_id.startswith(known) or known.startswith(container_id))
            for known in self.self_identity
        )

    def controllable(self, name: str, container_id: str = "") -> bool:
        """What ``ContainerInfo.controllable`` should say for this container.

        Kept in terms of :meth:`decide` so the flag a client greys a button out
        on cannot drift from the answer it would actually get.
        """
        return self.decide(name, container_id).allowed
