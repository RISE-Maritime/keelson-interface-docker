"""Translation from a container runtime's raw attributes into protobuf.

Deliberately pure: this module imports neither ``docker`` nor ``zenoh``, so the
bulk of the test suite exercises it with plain dictionaries. :mod:`backend`
produces a :class:`ContainerSnapshot` from whatever the runtime hands back; this
module turns that into a :class:`ContainerInfo` and nothing else touches the
wire types.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from google.protobuf.timestamp_pb2 import Timestamp

from .interfaces import (
    ContainerInfo,
    ContainerState,
    HealthStatus,
    LogLine,
    RestartPolicy,
)

# The Docker API reports "never happened" as the proto-zero instant rather than
# omitting the field. Passed through, it renders as a year-1 date in a UI.
_ZERO_TIMES = frozenset({"", "0001-01-01T00:00:00Z", "0001-01-01T00:00:00.000000000Z"})

# Docker's --timestamps prefix: RFC3339Nano, then a single space, then the line.
_LOG_PREFIX = re.compile(rb"^(\S+?Z)\s(.*)$", re.DOTALL)

_STATES = {
    "created": ContainerState.CONTAINER_STATE_CREATED,
    "running": ContainerState.CONTAINER_STATE_RUNNING,
    "paused": ContainerState.CONTAINER_STATE_PAUSED,
    "restarting": ContainerState.CONTAINER_STATE_RESTARTING,
    "removing": ContainerState.CONTAINER_STATE_REMOVING,
    "exited": ContainerState.CONTAINER_STATE_EXITED,
    "dead": ContainerState.CONTAINER_STATE_DEAD,
}

_RESTART_POLICIES = {
    # The Engine API spells "no restart policy" as the empty string, which is
    # indistinguishable from "not reported" by the time it reaches a UI. Both
    # spellings map to the explicit NO.
    "": RestartPolicy.RESTART_POLICY_NO,
    "no": RestartPolicy.RESTART_POLICY_NO,
    "always": RestartPolicy.RESTART_POLICY_ALWAYS,
    "unless-stopped": RestartPolicy.RESTART_POLICY_UNLESS_STOPPED,
    "on-failure": RestartPolicy.RESTART_POLICY_ON_FAILURE,
}

_HEALTH = {
    "starting": HealthStatus.HEALTH_STATUS_STARTING,
    "healthy": HealthStatus.HEALTH_STATUS_HEALTHY,
    "unhealthy": HealthStatus.HEALTH_STATUS_UNHEALTHY,
    "none": HealthStatus.HEALTH_STATUS_NONE,
}

COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"


@dataclass(frozen=True)
class ContainerSnapshot:
    """One container as the runtime described it, with nothing interpreted yet.

    ``image_tags`` and ``image_id`` are carried separately from ``attrs``
    because docker-py exposes them on the image object rather than in the
    container's attribute dictionary.
    """

    name: str
    id: str
    attrs: dict
    image_tags: Sequence[str] = ()
    image_id: str = ""
    labels: dict = field(default_factory=dict)


def parse_docker_time(value) -> Timestamp | None:
    """RFC3339(Nano) string to a Timestamp, or None when the runtime is saying
    "never".

    ``Timestamp.FromJsonString`` is used rather than ``datetime.fromisoformat``
    because Docker emits nine fractional digits, which ``fromisoformat`` rejects
    on every Python that ships today.
    """
    if not isinstance(value, str) or value in _ZERO_TIMES:
        return None
    ts = Timestamp()
    try:
        ts.FromJsonString(value)
    except ValueError:
        return None
    # A runtime that reports a differently-spelled zero instant still means
    # "never"; catch it after parsing rather than growing the literal set.
    if ts.seconds < 0 and ts.ToDatetime().year <= 1:
        return None
    return ts


def container_state(raw: str) -> int:
    return _STATES.get((raw or "").lower(), ContainerState.CONTAINER_STATE_UNSPECIFIED)


def restart_policy(raw) -> int:
    if raw is None:
        return RestartPolicy.RESTART_POLICY_UNSPECIFIED
    return _RESTART_POLICIES.get(str(raw).lower(), RestartPolicy.RESTART_POLICY_UNSPECIFIED)


def health_status(state: dict) -> int:
    """A container with no health check declares none -- which is a different
    answer from "the responder could not tell"."""
    health = (state or {}).get("Health")
    if not health:
        return HealthStatus.HEALTH_STATUS_NONE
    return _HEALTH.get(
        str(health.get("Status", "")).lower(), HealthStatus.HEALTH_STATUS_UNSPECIFIED
    )


def image_reference(snapshot: ContainerSnapshot) -> str:
    """The image as deployed.

    The old implementation was ``container.image.tags[0]``, which raises
    IndexError for an image pulled by digest or whose tag was pruned out from
    under it -- and took the entire listing down with it, not one row.
    """
    for tag in snapshot.image_tags or ():
        if tag:
            return tag
    configured = (snapshot.attrs.get("Config") or {}).get("Image")
    return configured or snapshot.image_id or ""


def build_container_info(snapshot: ContainerSnapshot, *, controllable: bool) -> ContainerInfo:
    attrs = snapshot.attrs or {}
    state = attrs.get("State") or {}
    host_config = attrs.get("HostConfig") or {}
    policy = host_config.get("RestartPolicy") or {}
    labels = snapshot.labels or (attrs.get("Config") or {}).get("Labels") or {}

    info = ContainerInfo(
        name=snapshot.name,
        id=snapshot.id,
        image=image_reference(snapshot),
        raw_state=str(state.get("Status", "") or ""),
        restart_policy=restart_policy(policy.get("Name")),
        restart_policy_max_retries=int(policy.get("MaximumRetryCount") or 0),
        restart_count=int(attrs.get("RestartCount") or 0),
        health=health_status(state),
        controllable=controllable,
        compose_project=str(labels.get(COMPOSE_PROJECT_LABEL, "") or ""),
        compose_service=str(labels.get(COMPOSE_SERVICE_LABEL, "") or ""),
    )
    info.state = container_state(info.raw_state)

    for field_name, raw in (
        ("created_at", attrs.get("Created")),
        ("started_at", state.get("StartedAt")),
        ("finished_at", state.get("FinishedAt")),
    ):
        parsed = parse_docker_time(raw)
        if parsed is not None:
            getattr(info, field_name).CopyFrom(parsed)

    # ExitCode is meaningless until the container has actually exited once; a
    # running container's 0 would read as "exited cleanly".
    if parse_docker_time(state.get("FinishedAt")) is not None:
        info.exit_code = int(state.get("ExitCode") or 0)

    return info


def matches_any(name: str, globs: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, g) for g in globs)


def parse_log_line(chunk: bytes, stream: int) -> LogLine | None:
    """One line of Docker ``--timestamps`` output to a LogLine, or None if blank.

    The single place the wire format is understood, so the pull path (the
    ``logs`` RPC, via :func:`parse_log_stream`) and the follow path
    (:mod:`logs_follower`) cannot drift into parsing it two different ways.

    ``errors="replace"`` is deliberate: a multibyte sequence split at a buffer
    boundary is normal, and a plain ``.decode("utf-8")`` turned it into a
    UnicodeDecodeError that escaped the callback so the RPC never replied at all.
    """
    if not chunk.strip():
        return None
    match = _LOG_PREFIX.match(chunk)
    text, ts = (
        (match.group(2), parse_docker_time(match.group(1).decode("ascii", "replace")))
        if match
        else (chunk, None)
    )
    line = LogLine(stream=stream, text=text.decode("utf-8", errors="replace").rstrip("\r"))
    if ts is not None:
        line.time.CopyFrom(ts)
    return line


def parse_log_stream(raw: bytes, stream: int) -> list[LogLine]:
    """Split one stream's ``--timestamps`` output into tagged LogLines."""
    if not raw:
        return []
    parsed = (parse_log_line(chunk, stream) for chunk in raw.split(b"\n"))
    return [line for line in parsed if line is not None]


def merge_log_lines(stdout: Sequence[LogLine], stderr: Sequence[LogLine]) -> list[LogLine]:
    """Interleave two streams by timestamp, keeping each stream's own order.

    A line without a timestamp (a continuation line, or a runtime that emitted
    none) inherits the previous timestamp in its own stream, so it sorts next to
    the line it belongs to instead of jumping to the front.
    """
    if not stderr:
        return list(stdout)
    if not stdout:
        return list(stderr)

    keyed: list[tuple[tuple[int, int], int, int, LogLine]] = []
    for stream_index, lines in enumerate((stdout, stderr)):
        carried = (0, 0)
        for position, line in enumerate(lines):
            if line.HasField("time"):
                carried = (line.time.seconds, line.time.nanos)
            keyed.append((carried, stream_index, position, line))
    keyed.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in keyed]


def cap_log_lines(
    lines: Sequence[LogLine], *, max_lines: int, max_bytes: int
) -> tuple[list[LogLine], bool]:
    """Trim to the most recent window. Returns ``(lines, truncated)``.

    The OLDEST lines are dropped, so the caller always gets the tail -- which is
    what "tail the logs" means, and what a reader looking for the most recent
    failure needs.
    """
    truncated = False
    kept = list(lines)
    if max_lines > 0 and len(kept) > max_lines:
        kept = kept[-max_lines:]
        truncated = True
    if max_bytes > 0:
        total = 0
        start = len(kept)
        for index in range(len(kept) - 1, -1, -1):
            total += len(kept[index].text.encode("utf-8")) + 1
            if total > max_bytes:
                break
            start = index
        if start > 0:
            kept = kept[start:]
            truncated = True
    return kept, truncated
