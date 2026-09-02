"""Test doubles. No docker daemon and no zenoh session are involved anywhere."""

from __future__ import annotations

from dataclasses import dataclass, field

from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from keelson_interface_docker.backend import BackendError
from keelson_interface_docker.model import ContainerSnapshot


def make_attrs(
    *,
    status: str = "running",
    created: str = "2026-01-02T03:04:05.123456789Z",
    started: str = "2026-01-02T03:04:06.000000000Z",
    finished: str = "0001-01-01T00:00:00Z",
    exit_code: int = 0,
    restart_policy: str = "unless-stopped",
    max_retries: int = 0,
    restart_count: int = 0,
    image: str = "ghcr.io/rise-maritime/thing:1.2.3",
    health: str | None = None,
    tty: bool = False,
    labels: dict | None = None,
) -> dict:
    state: dict = {
        "Status": status,
        "StartedAt": started,
        "FinishedAt": finished,
        "ExitCode": exit_code,
    }
    if health is not None:
        state["Health"] = {"Status": health}
    return {
        "Created": created,
        "State": state,
        "RestartCount": restart_count,
        "Config": {"Image": image, "Tty": tty, "Labels": labels or {}},
        "HostConfig": {"RestartPolicy": {"Name": restart_policy, "MaximumRetryCount": max_retries}},
    }


def snapshot(
    name: str = "thing",
    container_id: str = "a" * 64,
    *,
    image_tags: tuple[str, ...] = ("ghcr.io/rise-maritime/thing:1.2.3",),
    image_id: str = "sha256:deadbeef",
    labels: dict | None = None,
    **attr_kwargs,
) -> ContainerSnapshot:
    return ContainerSnapshot(
        name=name,
        id=container_id,
        attrs=make_attrs(labels=labels, **attr_kwargs),
        image_tags=image_tags,
        image_id=image_id,
        labels=labels or {},
    )


class FakeBackend:
    """Records every call, so a test can assert that a refused action never
    reached the daemon at all."""

    def __init__(self, snapshots=(), raises: Exception | None = None, logs=(b"", b"", False)):
        self.snapshots = list(snapshots)
        self.raises = raises
        self._logs = logs
        self.calls: list[tuple] = []

    def _maybe_raise(self):
        if self.raises is not None:
            raise self.raises

    def list(self, *, running_only=False, label=None):
        self.calls.append(("list", running_only, label))
        self._maybe_raise()
        if running_only:
            return [s for s in self.snapshots if s.attrs["State"]["Status"] == "running"]
        return list(self.snapshots)

    def get(self, name_or_id):
        self.calls.append(("get", name_or_id))
        self._maybe_raise()
        for s in self.snapshots:
            if name_or_id in (s.name, s.id):
                return s
        # Same shape the real backend produces, so handler tests exercise the
        # mapping the caller actually sees.
        raise BackendError(ErrorResponse.Code.NOT_FOUND, f"no such container: {name_or_id}")

    def logs(self, name, *, tail, since=None, want_stdout=True, want_stderr=True):
        self.calls.append(("logs", name, tail, since, want_stdout, want_stderr))
        self._maybe_raise()
        out, err, tty = self._logs
        return out, err, tty, self.get(name)

    def _act(self, verb, name, timeout_s=0):
        self.calls.append((verb, name, timeout_s))
        self._maybe_raise()
        current = self.get(name)
        # Flip the state so a test can prove the reply carries POST-action state.
        attrs = dict(current.attrs)
        attrs["State"] = dict(attrs["State"])
        attrs["State"]["Status"] = "exited" if verb == "stop" else "running"
        return ContainerSnapshot(
            name=current.name,
            id=current.id,
            attrs=attrs,
            image_tags=current.image_tags,
            image_id=current.image_id,
            labels=current.labels,
        )

    def start(self, name, timeout_s=0):
        return self._act("start", name, timeout_s)

    def stop(self, name, timeout_s=0):
        return self._act("stop", name, timeout_s)

    def restart(self, name, timeout_s=0):
        return self._act("restart", name, timeout_s)


@dataclass
class FakeOp:
    """Stands in for keelson.scaffolding.rpc.RpcOp."""

    procedure: str = "list"
    request_bytes: bytes = b""
    reply_key: str = "test/key"
    ok: object = None
    err: tuple[str, int] | None = None
    replies: int = field(default=0)

    def reply_ok(self, response=b""):
        self.replies += 1
        self.ok = response

    def reply_err(self, description: str, code: int = ErrorResponse.Code.UNSPECIFIED):
        self.replies += 1
        self.err = (description, code)
