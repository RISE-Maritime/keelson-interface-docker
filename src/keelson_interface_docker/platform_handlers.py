"""The ``platform_config/v1`` procedures.

Shaped exactly like :mod:`handlers` next door: one function per procedure, each
wrapped so that a :class:`RepoError` or :class:`PathError` becomes a typed
``reply_err`` and anything else propagates to ``serve_rpc`` as INTERNAL. The
invariant every test asserts is the same one -- **reply exactly once on every
path**.

READ AND WRITE ARE BOTH HERE, but only the read half is implemented so far;
the mutating procedures reply UNAVAILABLE rather than being absent, because
``serve_rpc``'s liveliness token advertises the COMPLETE interface. A procedure
that is declared and silently never answers is indistinguishable, from the
caller's side, from an unreachable host -- so an honest "not built yet" is the
only correct placeholder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from google.protobuf.timestamp_pb2 import Timestamp
from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from . import platform_repo as repo
from .interfaces import (
    DeleteFileRequest,
    EntityInfo,
    FileInfo,
    FileKind,
    ListEntitiesRequest,
    ListEntitiesResponse,
    ListFilesRequest,
    ListFilesResponse,
    ReadFileRequest,
    ReadFileResponse,
    RepoStatus,
    RepoStatusRequest,
    RepoStatusResponse,
    SyncRequest,
    WriteFileRequest,
    WriteFileResponse,
)
from .platform_guard import FileGuard
from .platform_paths import PathError, resolve
from .platform_write import TREE_LOCK, atomic_write, check_base_sha

logger = logging.getLogger("keelson-interface-docker.platform")


@dataclass(frozen=True)
class PlatformContext:
    """Everything the procedures need, and nothing else."""

    root: Path
    guard: FileGuard


def _ts(when: datetime | None) -> Timestamp | None:
    if when is None:
        return None
    stamp = Timestamp()
    stamp.FromDatetime(when.astimezone(UTC))
    return stamp


def _kind(name: str) -> int:
    """Presentation hint from the filename. A guess about VIEWING, not a parse.

    COMPOSE means "named like a compose file", never "valid compose" -- one file
    in the real repository is named like one and does not parse.
    """
    lower = name.lower()
    if lower.startswith("docker-compose") or lower == "compose.yml" or lower == "compose.yaml":
        return FileKind.FILE_KIND_COMPOSE
    if lower == ".env" or lower.startswith(".env."):
        return FileKind.FILE_KIND_ENV
    if lower.endswith((".yml", ".yaml")):
        return FileKind.FILE_KIND_YAML
    if lower.endswith((".json", ".json5")):
        return FileKind.FILE_KIND_JSON
    if lower.endswith(".md"):
        return FileKind.FILE_KIND_MARKDOWN
    return FileKind.FILE_KIND_OTHER


def _fill_repo_status(msg: RepoStatus, ctx: PlatformContext) -> repo.RepoState:
    state = repo.read_state(ctx.root)
    msg.branch = state.branch
    msg.head_sha = state.head_sha
    msg.remote_url = state.remote_url
    msg.ahead = state.ahead
    msg.behind = state.behind
    msg.dirty_paths.extend(state.dirty_paths)
    msg.detached = state.detached
    fetched = repo.last_fetch_at(ctx.root)
    if fetched is not None:
        msg.last_fetch_at.CopyFrom(_ts(fetched))
    return state


def _file_info(ctx: PlatformContext, path: Path, dirty: frozenset[str]) -> FileInfo:
    rel = repo.relative(ctx.root, path)
    info = FileInfo(
        name=path.name,
        relative_path=rel,
        size_bytes=path.stat().st_size,
        kind=_kind(path.name),
        dirty=rel in dirty,
        # Both from the guard, never derived from one another: the ordinary
        # deployment has everything writable and nothing deletable, so a client
        # that read one for the other would offer a Delete button that every
        # call refuses.
        writable=ctx.guard.writable(rel),
        deletable=ctx.guard.deletable(rel),
    )
    when = repo.modified_at(path)
    if when is not None:
        info.modified_at.CopyFrom(_ts(when))
    return info


def handle_list_entities(ctx: PlatformContext, op) -> None:
    # Best-effort, for the same reason as in write_file: a checkout whose git
    # cannot be read still has entities worth listing, and an operator is better
    # served by the list plus an unknown status than by nothing at all. The
    # status is left UNSET rather than defaulted -- an empty RepoStatus would
    # read as a clean tree on a branch called "", which is a claim, not an
    # absence.
    repo_state_msg = RepoStatus()
    try:
        state = _fill_repo_status(repo_state_msg, ctx)
        dirty = repo.dirty_set(state)
        have_status = True
    except repo.RepoError as exc:
        logger.warning("listing entities without repo state: %s", exc.message)
        dirty = frozenset()
        have_status = False

    response = ListEntitiesResponse(
        # The four gates, each read from the flag that governs it.
        write_enabled=ctx.guard.write_enabled,
        delete_enabled=ctx.guard.delete_enabled,
        git_enabled=ctx.guard.git_enabled,
        push_enabled=ctx.guard.push_enabled,
    )
    if have_status:
        response.repo.CopyFrom(repo_state_msg)
    response.observed_at.CopyFrom(_ts(datetime.now(tz=UTC)))

    for name in repo.list_entity_names(ctx.root):
        files = repo.list_entity_files(ctx.root, name)
        rel = repo.relative(ctx.root, repo.platforms_dir(ctx.root) / name)
        entity = EntityInfo(
            name=name,
            relative_path=rel,
            file_count=len(files),
            has_readme=repo.has_readme(files),
            dirty=repo.entity_is_dirty(rel, dirty),
        )
        # ABSENT IS NOT ZERO. Left unset when nothing parsed, so a client renders
        # a dash instead of asserting "0 services" about an unreadable file.
        services = repo.count_services(files)
        if services is not None:
            entity.service_count = services
        response.entities.append(entity)

    op.reply_ok(response)


def handle_list_files(ctx: PlatformContext, op) -> None:
    request = ListFilesRequest.FromString(op.request_bytes or b"")
    if not request.entity:
        raise repo.RepoError(ErrorResponse.Code.INVALID_ARGUMENT, "entity is required")

    # Refuse a caller-supplied entity that is not a plain directory name before
    # it is joined onto anything -- the same rule the path jail applies, one
    # level up.
    if "/" in request.entity or request.entity in {".", ".."}:
        raise repo.RepoError(
            ErrorResponse.Code.INVALID_ARGUMENT,
            "entity must be a directory name, not a path",
        )

    state = repo.read_state(ctx.root)
    dirty = repo.dirty_set(state)

    response = ListFilesResponse(entity=request.entity)
    response.observed_at.CopyFrom(_ts(datetime.now(tz=UTC)))
    for path in repo.list_entity_files(ctx.root, request.entity):
        response.files.append(_file_info(ctx, path, dirty))

    op.reply_ok(response)


def handle_read_file(ctx: PlatformContext, op) -> None:
    request = ReadFileRequest.FromString(op.request_bytes or b"")
    path = resolve(ctx.root, request.path, must_be_file=True)
    rel = repo.relative(ctx.root, path)

    content, truncated = repo.read_bytes(path)

    response = ReadFileResponse(
        path=rel,
        content=content,
        # The sha of what is RETURNED. For a truncated read that is the prefix's
        # sha, which cannot be replayed as a base_sha256 -- correct, because the
        # contract forbids writing a truncated file back at all.
        sha256=repo.sha256_of(content),
        size_bytes=path.stat().st_size,
        writable=ctx.guard.writable(rel),
        truncated=truncated,
    )
    when = repo.modified_at(path)
    if when is not None:
        response.modified_at.CopyFrom(_ts(when))

    op.reply_ok(response)


def handle_write_file(ctx: PlatformContext, op) -> None:
    request = WriteFileRequest.FromString(op.request_bytes or b"")

    # Resolve the path BEFORE consulting the guard, because the guard's globs are
    # written against repository-relative paths and a caller-supplied string is
    # not one until the jail has normalised it. must_be_file is False: a create
    # targets a path that does not exist yet.
    path = resolve(ctx.root, request.path)
    rel = repo.relative(ctx.root, path)

    decision = ctx.guard.decide_write(rel)
    if not decision.allowed:
        op.reply_err(decision.reason, decision.code)
        return

    # One writer at a time. Two saves arriving on two queryable threads would
    # otherwise interleave a read-compare-write against the same file.
    with TREE_LOCK:
        check_base_sha(path, request.base_sha256)
        atomic_write(path, request.content)

        response = WriteFileResponse(
            path=rel,
            sha256=repo.sha256_of(request.content),
            # Not git_enabled yet in this build: the file is written to the
            # working tree and nothing is committed. `pushed` stays false with an
            # EMPTY push_error, which the contract distinguishes from a push that
            # was attempted and failed.
            pushed=False,
        )

        # THE WRITE IS ALREADY DURABLE BY HERE, so a failure to read the tree's
        # state afterwards must not be reported as a failed save. Repo status is
        # decoration on this response; reporting UNAVAILABLE for a file that is
        # on disk would tell an operator their work was lost when it was not,
        # and send them back to SSH. Left unset instead, which a client renders
        # as "unknown" rather than as a clean tree.
        try:
            _fill_repo_status(response.repo, ctx)
        except repo.RepoError as exc:
            logger.warning("wrote %s but could not read repo state: %s", rel, exc.message)
            response.ClearField("repo")

    logger.info(
        "wrote %s (%d bytes) for operator %r", rel, len(request.content), request.operator_id
    )
    op.reply_ok(response)


def handle_repo_status(ctx: PlatformContext, op) -> None:
    response = RepoStatusResponse(
        write_enabled=ctx.guard.write_enabled,
        delete_enabled=ctx.guard.delete_enabled,
        git_enabled=ctx.guard.git_enabled,
        push_enabled=ctx.guard.push_enabled,
    )
    _fill_repo_status(response.repo, ctx)
    op.reply_ok(response)


def _not_built(name: str):
    """A declared procedure that is not implemented yet.

    UNAVAILABLE, not silence. ``serve_rpc`` advertises the complete interface,
    so a procedure that never replies is indistinguishable from an unreachable
    responder; an honest refusal names itself.
    """

    def _handler(ctx: PlatformContext, op) -> None:
        raise repo.RepoError(
            ErrorResponse.Code.UNAVAILABLE,
            f"{name} is declared by this interface but not implemented in this build",
        )

    return _handler


def _guarded(fn, ctx: PlatformContext):
    """Translate the two typed failures; let everything else reach serve_rpc.

    Same contract as ``handlers._guarded``: exactly one reply on every path.
    """

    def _run(op) -> None:
        try:
            fn(ctx, op)
        except PathError as exc:
            op.reply_err(str(exc), ErrorResponse.Code.INVALID_ARGUMENT)
        except repo.RepoError as exc:
            op.reply_err(exc.message, exc.code)

    return _run


def build(ctx: PlatformContext) -> tuple[dict, dict]:
    """Return ``(handlers, summarizers)`` for ``serve_rpc``.

    All seven procedures are present, because the liveliness token claims all
    seven. The three mutating ones answer UNAVAILABLE until ``gitops`` lands.
    """
    handlers = {
        "list_entities": _guarded(handle_list_entities, ctx),
        "list_files": _guarded(handle_list_files, ctx),
        "read_file": _guarded(handle_read_file, ctx),
        "repo_status": _guarded(handle_repo_status, ctx),
        "write_file": _guarded(handle_write_file, ctx),
        "delete_file": _guarded(_not_built("delete_file"), ctx),
        "sync": _guarded(_not_built("sync"), ctx),
    }

    def _summary(request_cls, *fields):
        def _fmt(raw: bytes) -> str:
            try:
                request = request_cls.FromString(raw or b"")
            except Exception:
                return "<undecodable>"
            return ", ".join(
                f"{f}={getattr(request, f)!r}" for f in fields if getattr(request, f, None)
            )

        return _fmt

    summarizers = {
        "list_entities": _summary(ListEntitiesRequest),
        "list_files": _summary(ListFilesRequest, "entity"),
        "read_file": _summary(ReadFileRequest, "path"),
        "repo_status": _summary(RepoStatusRequest),
        "write_file": _summary(WriteFileRequest, "path", "commit_message", "operator_id"),
        "delete_file": _summary(DeleteFileRequest, "path", "operator_id"),
        "sync": _summary(SyncRequest),
    }
    return handlers, summarizers
