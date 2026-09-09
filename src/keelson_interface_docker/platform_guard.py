"""Who is allowed to change what in the platforms repository.

The sibling of :mod:`guard`, for ``platform_config/v1``, and written to the same
rules: default deny, one opt-in per privilege class, the decision made before the
filesystem is touched, and every gate reflected back in the response so a client
greys a control rather than discovering a refusal on the operator's click.

FOUR GATES, NOT ONE, and they are four different questions:

``--allow-write``
    May a file be changed at all. Off by default.
``--allow-delete``
    May a file be removed. Requires write, and is NOT implied by it: deletion is
    the only irreversible verb here, and "edit anything, delete nothing" is what
    nearly every deployment actually wants.
``--allow-git``
    Is a change committed, or only written to the working tree. Requires write.
``--allow-push``
    Is a commit published to the remote -- where every other platform will pull
    it. Requires git, and is the only gate that reaches beyond this host.

THE ORDINARY DEPLOYMENT HAS THEM IN A MIXED STATE: write on, delete off, git on,
push off. That is why none may be derived from another. A client greying its
Save button on ``git_enabled``, or offering Delete because ``write_enabled`` is
set, is reading the wrong field and will offer actions every call refuses.

WHY THIS MATTERS MORE HERE THAN FOR CONTAINERS. This process already mounts the
Docker socket, which makes it root-equivalent on its host. Giving the same
process a credential that can push to the organisation's repository merges two
trust boundaries that were separate. The recommended shape for any host that
enables ``--allow-push`` is therefore two containers from this one image -- one
with the socket and no ``--platforms-root``, one with the checkout and the key
and no socket -- and these gates are what make that split expressible rather
than aspirational.

Pure -- imports neither ``zenoh``, ``docker`` nor ``git`` -- so the policy is
testable without any of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from .platform_paths import path_matches


@dataclass(frozen=True)
class Decision:
    """The answer to "may I change this file?".

    ``reason`` names *which* gate refused, because the operator's next action
    differs: turn writing on, widen the path allow-list, enable committing, or
    accept that this host does not publish.
    """

    allowed: bool
    reason: str = ""
    code: int = ErrorResponse.Code.PERMISSION_DENIED


ALLOWED = Decision(allowed=True)


@dataclass(frozen=True)
class FileGuard:
    """Read-only unless told otherwise, then only for named paths."""

    #: False (the default) makes every mutating procedure reply
    #: PERMISSION_DENIED. Reading is not gated beyond the path jail: browsing the
    #: fleet's configuration is the point, and a responder that cannot be read
    #: has nothing to offer.
    write_enabled: bool = False

    #: Segment-aware globs against the repository-relative path. Never empty
    #: when ``write_enabled`` is set -- ``app.py`` refuses that combination at
    #: startup rather than presenting a responder that looks enabled and refuses
    #: everything, exactly as ``--allow-control`` does.
    write_globs: tuple[str, ...] = ()

    #: Globs naming what ``delete_file`` may remove. EMPTY IS THE SWITCH: there
    #: is no separate ``delete_enabled`` boolean that could disagree with it.
    #:
    #: Independent of :attr:`write_globs` rather than a subset, for the same
    #: reason ``remove_globs`` is independent of ``allow_globs`` next door:
    #: "edit every entity, delete only in the scratch one" is a real
    #: configuration and is unsayable if one list must contain the other.
    delete_globs: tuple[str, ...] = ()

    #: Whether a write is committed. Requires :attr:`write_enabled`.
    git_enabled: bool = False

    #: Whether a commit is pushed. Requires :attr:`git_enabled`.
    #:
    #: The only gate whose effect leaves this machine, which is why it is last
    #: and separate: enabling committing so an operator can inspect ``git log``
    #: must not silently also publish to the repository every other platform
    #: pulls from.
    push_enabled: bool = False

    @property
    def delete_enabled(self) -> bool:
        """What ``ListEntitiesResponse.delete_enabled`` should say.

        Derived, not stored, and reads both: deletion additionally requires
        writing to be on (``app.py`` refuses the combination at startup).
        """
        return self.write_enabled and bool(self.delete_globs)

    def decide_write(self, relative: str) -> Decision:
        """Whether *relative* may be written.

        Evaluated before the file is looked up, so a refusal cannot be used to
        probe whether a given path exists in the checkout.
        """
        if not self.write_enabled:
            return Decision(
                allowed=False,
                reason=(
                    "this responder is read-only "
                    "(start it with --allow-write and --allow-path GLOB)"
                ),
            )
        return self._against(self.write_globs, "write", relative)

    def decide_delete(self, relative: str) -> Decision:
        """Whether *relative* may be deleted.

        Never falls through to :meth:`decide_write`. Sharing the code would mean
        sharing the allow-list, and the entire point is that they are different
        questions with different consequences.
        """
        if not self.write_enabled:
            return Decision(
                allowed=False,
                reason=(
                    "this responder is read-only "
                    "(start it with --allow-write, then --allow-delete GLOB)"
                ),
            )

        if not self.delete_globs:
            return Decision(
                allowed=False,
                reason=(
                    "file deletion is disabled on this responder; enabling "
                    "editing does not enable it (start it with --allow-delete GLOB)"
                ),
            )

        return self._against(self.delete_globs, "delete", relative)

    def _against(self, globs: tuple[str, ...], list_name: str, relative: str) -> Decision:
        if not any(path_matches(relative, g) for g in globs):
            allowed = ", ".join(globs) or "<none>"
            return Decision(
                allowed=False,
                reason=(
                    f"{relative!r} is not in this responder's {list_name} allow-list ({allowed})"
                ),
            )
        return ALLOWED

    def writable(self, relative: str) -> bool:
        """What ``FileInfo.writable`` should say for this path.

        Kept in terms of :meth:`decide_write` so the flag a client greys a
        button on cannot drift from the answer the call would actually give.
        """
        return self.decide_write(relative).allowed

    def deletable(self, relative: str) -> bool:
        """What ``FileInfo.deletable`` should say for this path.

        In terms of :meth:`decide_delete`, and reported separately from
        :meth:`writable` because a client that conflates them offers a Delete
        button that every call refuses.
        """
        return self.decide_delete(relative).allowed
