"""The startup gates, exercised by actually running the console script.

Everything else in this suite calls into the package. These four paths only
exist in ``main()`` -- argparse validation and the pre-flight socket check --
and a unit test that imports ``app`` cannot reach them, because they are about
the process exiting before it ever opens a Zenoh session.

No Docker daemon is required: the failure branch is driven by pointing
``DOCKER_HOST`` at a socket that does not exist.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from .conftest import console_script

pytestmark = pytest.mark.unit

APP = console_script("keelson-interface-docker")
BASE = [APP, "-r", "test", "-e", "entity", "-s", "source"]


def run(args, env=None, timeout=60):
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, env=env, check=False
    )


class TestArgumentValidation:
    def test_allow_control_without_a_glob_is_rejected(self):
        # A responder started with control "enabled" and nothing allowed would
        # look enabled and refuse everything. argparse.error exits 2, before
        # logging setup or any socket contact.
        result = run([*BASE, "--allow-control"])
        assert result.returncode == 2
        assert "--allow-control requires at least one --allow GLOB" in result.stderr

    def test_allow_control_with_a_glob_gets_past_argument_parsing(self, fake_docker_env):
        # Same flags, one --allow added: it must now fail (or not) for reasons
        # other than argument validation.
        result = run([*BASE, "--allow-control", "--allow", "x-*"], env=fake_docker_env)
        assert result.returncode != 2
        assert "requires at least one --allow" not in result.stderr

    def test_allow_remove_without_allow_control_is_rejected(self):
        # Removal without control would also skip build_guard's self-identity
        # resolution, leaving the responder able to delete its own container.
        result = run([*BASE, "--allow-remove", "scratch-*"])
        assert result.returncode == 2
        assert "--allow-remove requires --allow-control" in result.stderr

    def test_allow_remove_alongside_control_gets_past_argument_parsing(self, fake_docker_env):
        result = run(
            [*BASE, "--allow-control", "--allow", "x-*", "--allow-remove", "x-*"],
            env=fake_docker_env,
        )
        assert result.returncode != 2
        assert "--allow-remove requires" not in result.stderr

    @pytest.mark.parametrize("missing", ["-r", "-e", "-s"])
    def test_identity_arguments_are_required(self, missing):
        args = list(BASE)
        index = args.index(missing)
        del args[index : index + 2]
        result = run(args)
        assert result.returncode == 2

    def test_help_lists_the_control_flags(self):
        result = run([APP, "--help"])
        assert result.returncode == 0
        for flag in ("--allow-control", "--allow", "--allow-remove", "--self-container-name"):
            assert flag in result.stdout

    def test_help_lists_the_stats_flags(self):
        result = run([APP, "--help"])
        assert result.returncode == 0
        for flag in ("--publish-stats", "--stats-interval-s"):
            assert flag in result.stdout


class TestSocketPreflight:
    def test_an_unreachable_socket_exits_with_actionable_advice(self):
        # The container's most likely misconfiguration by far: the socket is
        # not mounted, or uid 10001 is not in the docker group. Exiting at
        # startup beats serving and answering UNAVAILABLE to every call.
        result = run(
            [*BASE],
            env={**os.environ, "DOCKER_HOST": "unix:///nonexistent/docker.sock"},
        )
        assert result.returncode == 1
        assert "cannot reach the container runtime" in result.stderr
        # The message has to name the two things the operator can act on.
        assert "DOCKER_GID" in result.stderr
        assert "/var/run/docker.sock" in result.stderr

    def test_a_reachable_socket_gets_past_the_preflight(self, fake_docker_env):
        # Started with no --listen and no router to scout, so it will sit in its
        # serve loop; the point is only that it did not exit 1 at the gate.
        proc = subprocess.Popen(
            [*BASE],
            env=fake_docker_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                proc.wait(timeout=10)
        finally:
            proc.kill()
            _, stderr = proc.communicate(timeout=30)
        assert "cannot reach the container runtime" not in stderr
        assert "Serving RPC interface container_control/v1" in stderr
