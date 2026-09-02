# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

# uv for a fast, apt-free install. No tini: zombie reaping and SIGTERM
# forwarding come from Docker's built-in init (compose `init: true`), which is
# what lets GracefulShutdown retract the liveliness tokens on `docker stop`
# instead of being SIGKILLed after the grace period.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 1) Third-party dependencies, in a layer keyed ONLY on pyproject.toml. Editing
#    application code does not re-resolve or re-download them.
COPY pyproject.toml README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --compile-bytecode -r pyproject.toml

# 2) Just this package; the dependencies above already satisfy it, so this layer
#    does no network I/O and is the only one a code change reruns.
#    --compile-bytecode matters here specifically: the container runs with a
#    read-only root filesystem, so Python cannot write __pycache__ at import
#    time and would otherwise re-parse every module on every start.
COPY src src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-deps --compile-bytecode .

# Non-root. NOTE this uid is not in the host's `docker` group and so cannot open
# a root:docker 0660 /var/run/docker.sock on its own -- the compose file's
# `group_add: ["${DOCKER_GID}"]` is what actually grants that. See the README.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app

# Visibility for a socket that disappears AFTER startup -- a daemon restart, a
# changed docker gid. Without it the process keeps serving, every RPC returns
# UNAVAILABLE, and `docker ps` still says healthy. It lives here rather than in
# a compose `healthcheck:` block so the six keelson-platforms files inherit it
# instead of duplicating it eight times.
#
# --timeout exceeds the probe's own 5s client budget, so a hung daemon yields a
# readable message rather than a silent SIGKILL. --retries 3 stops a momentary
# `systemctl restart docker` flapping the container.
#
# This is visibility only: `restart: unless-stopped` reacts to a container
# exiting, not to it going unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["container-control-healthcheck"]

ENTRYPOINT ["keelson-interface-docker"]
# -r/-e/-s are required, so a bare `docker run` cannot do anything useful. Say
# so rather than failing with an argparse error nobody asked for.
CMD ["--help"]
