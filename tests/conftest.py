import os
import shutil
import sys
from pathlib import Path

import pytest

from keelson_interface_docker.guard import ControlGuard
from keelson_interface_docker.handlers import Context, Limits

from .fakes import FakeBackend, snapshot


@pytest.fixture
def snapshots():
    return [
        snapshot("keelson-router", "r" * 64, status="running"),
        snapshot(
            "grafana", "g" * 64, status="exited", finished="2026-01-03T00:00:00Z", exit_code=137
        ),
        snapshot("keelson-interface-docker", "s" * 64, status="running"),
    ]


@pytest.fixture
def backend(snapshots):
    return FakeBackend(snapshots)


@pytest.fixture
def readonly_ctx(backend):
    return Context(backend=backend, guard=ControlGuard(), limits=Limits())


@pytest.fixture
def control_ctx(backend):
    return Context(
        backend=backend,
        guard=ControlGuard(
            control_enabled=True,
            allow_globs=("keelson-*",),
            self_identity=frozenset({"keelson-interface-docker", "s" * 64}),
        ),
        limits=Limits(),
    )


@pytest.fixture
def fake_engine():
    """A stub Docker Engine on a unix socket.

    Lets the subprocess tests run a real ``keelson-interface-docker`` process on
    a machine with no Docker daemon -- and in CI, where mounting the runner's
    socket into a test would be both unavailable and a bad idea.
    """
    from .fake_engine import FakeEngine

    with FakeEngine() as engine:
        yield engine


@pytest.fixture
def fake_docker_env(fake_engine):
    """``os.environ`` plus a DOCKER_HOST pointing at :func:`fake_engine`.

    DOCKER_HOST rather than a ``--docker-host`` flag: it is docker-py's own
    documented knob and ``docker.from_env()`` already honours it, so the
    responder needs no production surface that exists only for tests.
    """
    return {**os.environ, "DOCKER_HOST": fake_engine.docker_host}


def console_script(name: str) -> str:
    """Absolute path to one of this package's installed console scripts.

    Resolved next to ``sys.executable`` rather than found on PATH: pytest is
    normally invoked as ``.venv/bin/python -m pytest``, which does NOT put
    ``.venv/bin`` on PATH, so a bare name raises FileNotFoundError. Falls back
    to PATH for an environment (the container image) where the interpreter and
    the scripts live apart.
    """
    candidate = Path(sys.executable).parent / name
    if candidate.exists():
        return str(candidate)
    found = shutil.which(name)
    if found is None:  # pragma: no cover - a broken install, not a test case
        raise RuntimeError(f"console script {name!r} is not installed")
    return found
