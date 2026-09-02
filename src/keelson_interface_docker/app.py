"""Keelson RPC responder exposing this host's containers as container_control/v1.

Serves five procedures -- list, logs, start, stop, restart -- on the keelson RPC
key space:

    {realm}/@v0/{entity_id}/@rpc/container_control/v1/{procedure}/{source_id}

READ-ONLY BY DEFAULT. Mounting the Docker socket makes this process
root-equivalent on its host, so the mutating procedures refuse with
PERMISSION_DENIED until it is started with --allow-control and an explicit
--allow allow-list.
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import ExitStack
from pathlib import Path

import keelson
import zenoh
from keelson.scaffolding import (
    GracefulShutdown,
    add_common_arguments,
    create_zenoh_config,
    declare_liveliness,
    serve_rpc,
    setup_logging,
)

from . import handlers, logs_follower, selfid, status_publisher
from .backend import BackendError, DockerBackend, snapshots_by_label
from .guard import ControlGuard
from .interfaces import INTERFACE, VERSION

logger = logging.getLogger("keelson-interface-docker")

#: Shipped inside the package by scripts/generate_protos.sh. Registering it
#: makes construct_rpc_key() stop warning that container_control/v1 is not
#: well known, and is the single line that moves upstream when the interface
#: lands in keelson's own messages/interfaces.yaml.
INTERFACES_YAML = Path(__file__).parent / "interfaces" / "interfaces.yaml"

#: The pub/sub half of the same registry, shipped the same way. Registering the
#: subject stops construct_pubsub_key() warning, and registering the descriptor
#: set alongside it is what lets a subscriber -- and keelson2mcap, through
#: --extra-subjects-types -- DECODE the payload rather than just name it.
SUBJECTS_YAML = Path(__file__).parent / "interfaces" / "subjects.yaml"
PROTO_DESCRIPTOR_SET = Path(__file__).parent / "interfaces" / "ContainerControl.desc"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keelson-interface-docker",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=__doc__,
    )
    add_common_arguments(parser)

    parser.add_argument("-r", "--realm", type=str, required=True, help="Keelson base path.")
    parser.add_argument("-e", "--entity-id", type=str, required=True)
    parser.add_argument("-s", "--source-id", type=str, required=True, help="Responder id.")

    control = parser.add_argument_group("container control (off by default)")
    control.add_argument(
        "--allow-control",
        action="store_true",
        help=(
            "Permit start/stop/restart. Requires at least one --allow. Without "
            "it this responder answers list and logs only."
        ),
    )
    control.add_argument(
        "--allow",
        metavar="GLOB",
        action="append",
        default=[],
        help=(
            "Container NAME glob that may be controlled; repeatable. Use '*' to "
            "mean every container, deliberately."
        ),
    )
    control.add_argument(
        "--self-container-name",
        type=str,
        default=None,
        help=(
            "This responder's own container_name. Set it to the same literal as "
            "your compose file's container_name: so it can refuse to stop itself."
        ),
    )

    status = parser.add_argument_group("container status (on by default)")
    status.add_argument(
        "--publish-status",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Publish the container set as the 'container_status' subject "
            "whenever it changes, so consoles subscribe instead of polling "
            "list() per host. ON BY DEFAULT, unlike --allow-control and "
            "--follow-logs: those are off because they are privileged (one "
            "mutates the host, the other republishes container stdout). This "
            "publishes precisely the bytes list() already hands to any bus "
            "participant who asks -- the same answer, on time, not a wider one."
        ),
    )
    status.add_argument(
        "--status-interval-s",
        type=float,
        default=5.0,
        help=(
            "How often the container set is snapshotted and compared. This is "
            "the worst-case latency of a state change reaching a console, and "
            "it must beat the poll it replaces to be an improvement."
        ),
    )
    status.add_argument(
        "--status-heartbeat-s",
        type=float,
        default=30.0,
        help=(
            "Republish unchanged state at most this often. Zenoh pub/sub does "
            "not backfill, so this bounds how stale a late subscriber's first "
            "value is."
        ),
    )

    capture = parser.add_argument_group("log capture (off by default)")
    capture.add_argument(
        "--follow-logs",
        metavar="GLOB",
        action="append",
        default=[],
        help=(
            "Follow the logs of containers whose NAME matches, publishing them "
            "as the 'log_message' subject so the fleet's MCAP recorder captures "
            "them. Repeatable. Deliberately independent of --allow-control: "
            "recording a container's output is a different decision from being "
            "allowed to restart it, and a read-only responder must still be "
            "able to capture."
        ),
    )
    capture.add_argument("--follow-rescan-s", type=float, default=10.0)
    capture.add_argument(
        "--follow-max-lines-per-s",
        type=int,
        default=200,
        help="Per-container ceiling. Excess is dropped and reported in-band.",
    )
    capture.add_argument("--follow-queue-size", type=int, default=10_000)
    capture.add_argument(
        "--follow-tail",
        type=int,
        default=0,
        help="Lines of history to replay when a follow starts. 0 starts at the end.",
    )

    limits = parser.add_argument_group("limits")
    limits.add_argument("--stop-timeout-s", type=int, default=10)
    limits.add_argument("--default-tail-lines", type=int, default=200)
    limits.add_argument("--max-tail-lines", type=int, default=5000)
    limits.add_argument("--max-log-bytes", type=int, default=1_000_000)

    return parser


def build_guard(args: argparse.Namespace, backend: DockerBackend) -> ControlGuard:
    """Resolve self-identity and assemble the guard, or exit."""
    if not args.allow_control:
        # Read-only needs no self-identity: nothing is controllable anyway.
        return ControlGuard(control_enabled=False)

    identity, how = selfid.resolve(
        args.self_container_name,
        lookup=backend.get,
        list_by_label=lambda label: snapshots_by_label(backend, label),
    )
    if not identity:
        sys.exit(
            "Cannot determine which container is my own, and --allow-control is set:\n"
            "a stop/restart of this container would kill the responder mid-call and it\n"
            "would not come back until its restart policy fired. Pass\n"
            "--self-container-name <the container_name: from your compose file>."
        )

    logger.info("Self-container resolved via %s as: %s", how, ", ".join(sorted(identity)))
    return ControlGuard(
        control_enabled=True,
        allow_globs=tuple(args.allow),
        self_identity=identity,
    )


def run(session: zenoh.Session, args: argparse.Namespace, ctx: handlers.Context) -> None:
    procedures, summarizers = handlers.build(ctx)

    # A subject-level token per published subject, and only when we actually
    # publish -- a responder that captures nothing must not advertise that it
    # might. (serve_rpc declares the interface-level token itself, so it is not
    # passed here.)
    published_subjects = []
    if args.publish_status:
        published_subjects.append(status_publisher.SUBJECT)
    if args.follow_logs:
        published_subjects.append(logs_follower.SUBJECT)

    with declare_liveliness(
        session,
        args.realm,
        args.entity_id,
        args.source_id,
        pubsub_subjects=published_subjects,
    ):
        serve_rpc(
            session,
            base_path=args.realm,
            entity_id=args.entity_id,
            responder_id=args.source_id,
            interface=INTERFACE,
            version=VERSION,
            handlers=procedures,
            summarizers=summarizers,
            log=logger,
        )

        if ctx.guard.control_enabled:
            logger.warning(
                "Container control is ENABLED for names matching: %s",
                ", ".join(ctx.guard.allow_globs),
            )
        else:
            logger.info(
                "Read-only: start/stop/restart will reply PERMISSION_DENIED. "
                "Pass --allow-control with one or more --allow GLOB to enable them."
            )

        # Inside the liveliness context, so the subject token is up before the
        # first line is published and comes down after the last.
        with ExitStack() as stack:
            if args.publish_status:
                stack.enter_context(
                    status_publisher.ContainerStatusPublisher(
                        ctx.backend,
                        ctx.guard,
                        session,
                        base_path=args.realm,
                        entity_id=args.entity_id,
                        source_id=args.source_id,
                        interval_s=args.status_interval_s,
                        heartbeat_s=args.status_heartbeat_s,
                    )
                )
            if args.follow_logs:
                stack.enter_context(
                    logs_follower.LogFollower(
                        ctx.backend,
                        session,
                        base_path=args.realm,
                        entity_id=args.entity_id,
                        source_id=args.source_id,
                        globs=tuple(args.follow_logs),
                        rescan_s=args.follow_rescan_s,
                        max_lines_per_s=args.follow_max_lines_per_s,
                        queue_size=args.follow_queue_size,
                        tail=args.follow_tail,
                    )
                )

            # zenoh serves the queryables on its own callback threads; this
            # thread exists only to hold the session open until asked to stop.
            # SIGTERM (what `docker stop` sends) reaches GracefulShutdown, so
            # the liveliness tokens are retracted instead of expiring by lease.
            with GracefulShutdown() as shutdown:
                while not shutdown.is_requested():
                    shutdown.wait(1.0)

    logger.info("Shutting down")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Fail at startup, not on the first refused call: a responder started with
    # --allow-control and no globs would look enabled and refuse everything.
    if args.allow_control and not args.allow:
        parser.error("--allow-control requires at least one --allow GLOB")

    setup_logging(level=args.log_level)
    zenoh.init_log_from_env_or(logging.getLevelName(args.log_level))

    keelson.add_well_known_interfaces(INTERFACES_YAML)
    keelson.add_well_known_subjects_and_proto_definitions(SUBJECTS_YAML, PROTO_DESCRIPTOR_SET)

    backend = DockerBackend()
    try:
        backend.ping()
    except BackendError as exc:
        sys.exit(
            f"{exc.message}\n"
            "This responder needs the Docker socket bind-mounted and readable by "
            "its uid.\nSee the README: mount /var/run/docker.sock and set "
            "DOCKER_GID in your .env."
        )

    ctx = handlers.Context(
        backend=backend,
        guard=build_guard(args, backend),
        limits=handlers.Limits(
            stop_timeout_s=args.stop_timeout_s,
            default_tail_lines=args.default_tail_lines,
            max_tail_lines=args.max_tail_lines,
            max_log_bytes=args.max_log_bytes,
        ),
    )

    zconf = create_zenoh_config(mode=args.mode, connect=args.connect, listen=args.listen)

    logger.info("Opening Zenoh session...")
    with zenoh.open(zconf) as session:
        try:
            run(session, args, ctx)
        except KeyboardInterrupt:
            logger.info("Shutting down on user request")


if __name__ == "__main__":
    main()
