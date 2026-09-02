# keelson-interface-docker

A keelson RPC responder that exposes one host's containers on the bus: list
them, tail their logs, start / stop / restart them.

It serves the **`container_control/v1`** interface, so its keys are:

```
{realm}/@v0/{entity_id}/@rpc/container_control/v1/{procedure}/{source_id}
```

for example `rise/@v0/masslab/@rpc/container_control/v1/list/masslab-4`.

> **Read-only by default.** Mounting the Docker socket makes this process
> root-equivalent on its host. `start`, `stop` and `restart` refuse with
> `PERMISSION_DENIED` until it is started with `--allow-control` *and* an
> explicit `--allow` allow-list. See [Safety model](#safety-model).

## Procedures

| Procedure | Request | Reply | Notes |
|---|---|---|---|
| `list` | `ListContainersRequest{running_only, name_glob}` | `ListContainersResponse{containers, observed_at, control_enabled}` | An empty payload is a valid "list everything". |
| `logs` | `GetLogsRequest{name, tail_lines, since, stream}` | `GetLogsResponse{name, id, lines, truncated, tail_lines}` | Lines are tagged stdout/stderr and timestamped. |
| `start` | `StartContainerRequest{name}` | `ContainerActionResponse{container}` | Idempotent. |
| `stop` | `StopContainerRequest{name, timeout_s}` | `ContainerActionResponse{container}` | Idempotent. |
| `restart` | `RestartContainerRequest{name, timeout_s}` | `ContainerActionResponse{container}` | |

The contract is [`interfaces/ContainerControl.proto`](interfaces/ContainerControl.proto).
Two things about it are worth knowing before you write a client:

- **Containers are addressed by name, never by id.** The id changes on every
  `docker compose up --force-recreate`, so a client that round-trips an id from
  a `list` will get `NOT_FOUND` for a container plainly on its screen the moment
  the operator redeploys. `ContainerInfo` still returns the id, for display and
  for correlating with `docker ps`.
- **A refusal is a normal reply, not a fault.** Read
  `ListContainersResponse.control_enabled` and `ContainerInfo.controllable` and
  grey the button out, rather than discovering the refusal on the operator's
  click.

Every action reply carries the container's state *after* the operation, so a
client never has to follow an action with a `list` and race the runtime for the
answer.

## Safety model

The `/var/run/docker.sock` bind mount is the whole security story: anything that
can reach the Engine API through it can start a privileged container with `/`
bind-mounted. Treat this responder as a root shell on its host that happens to
speak protobuf.

The previous version of this interface exposed exactly that to any peer that
could reach one zenoh key, with no check of any kind. What replaces it:

1. **Read-only by default.** Without `--allow-control`, the three mutating
   procedures refuse *before touching the socket* — so a refused call cannot
   even be used to probe which containers exist on the host.
2. **An explicit allow-list.** `--allow-control` requires at least one
   `--allow GLOB`, matched with `fnmatch` against the container **name**.
   Starting with control enabled and nothing allowed is rejected at startup
   rather than producing a responder that looks enabled and refuses everything.
   `--allow '*'` is how you say "everything", deliberately.
3. **Self-protection.** The responder refuses to stop or restart its own
   container even when a glob matches it — that call would kill the responder
   mid-flight, and the caller would see a transport timeout rather than an
   answer.

Refusals come back as `ErrorResponse.PERMISSION_DENIED` with a description
naming *which* rule fired, because the operator's next move differs in each case.

### Why the allow-list matches names, not labels

Docker labels are authoritative and rename-immune, and they were considered. But
they require editing the compose file of every container you want to manage —
and the point of this interface is managing containers you did not author. The
name is the handle `docker ps`, compose's `container_name:` and the operator all
already use. If name churn becomes a problem (compose's generated
`project-service-1` names), a label predicate is the v2 answer; do not smuggle
one in as a `label:key=value` string inside `--allow`.

### Do not put the zenoh router in the allow-list

You would be able to stop it exactly once. The bus you would need in order to
start it again goes down with it.

### Self-identification

Three strategies, tried in order; the one that won is logged at startup.

1. `--self-container-name` — set it to the same literal as your compose file's
   `container_name:`. This is the documented path.
2. `/proc/self/mountinfo` (then `/proc/self/cgroup`) — Docker bind-mounts
   `/etc/hostname` out of `/var/lib/docker/containers/<id>/`, so the full id is
   readable there.
3. The `keelson.container_control.self=1` label, accepted only if **exactly
   one** container carries it.

`$HOSTNAME` is deliberately *not* used: it is the short container id only when
Docker sets the container's hostname, and this interface runs with
`network_mode: host`, where the container inherits the **host's** hostname.

If `--allow-control` is set and none of the three resolves, the process exits
rather than run without self-protection.

### Hardening further

For a genuinely least-privilege deployment, put a socket proxy
(`tecnativa/docker-socket-proxy`) in front, configured to allow `GET
/containers/*` and deny `POST`. That is a second container on every platform, so
it is not the default here, but it is the right answer where the host matters.

## Running it

```yaml
services:
  keelson-interface-docker:
    image: ghcr.io/rise-maritime/keelson-interface-docker:0.1.0-pre.2
    container_name: keelson-interface-docker
    restart: unless-stopped
    init: true                      # forwards SIGTERM to PID 1 — see below
    network_mode: host
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    group_add:
      - "${DOCKER_GID:-0}"
    labels:
      keelson.container_control.self: "1"
    command: >
      -r rise -e masslab -s masslab-4
      --mode peer --connect tcp/127.0.0.1:7447
      --self-container-name keelson-interface-docker
```

See [docker-compose.docker.yml](docker-compose.docker.yml)
for the full version, which also sets `read_only`, `cap_drop` and log rotation.

**Set `DOCKER_GID` on Linux.** The image runs as uid 10001, which is not in the
host's `docker` group and so cannot open a `root:docker 0660` socket. The gid
differs per host (999 on Debian/Ubuntu, something else on RHEL-family), so it is
not guessed:

```bash
echo "DOCKER_GID=$(getent group docker | cut -d: -f3)" > .env
```

It defaults to `0` rather than being a required variable, and getting it wrong
is not silent: gid 0 does not open that socket either, so the responder exits at
startup naming `DOCKER_GID`. The check lives in the process, where it can see
the actual socket, rather than in Compose where it can only see a variable —
and a `${DOCKER_GID:?}` guard in the base file would make the macOS path below
impossible, because Compose interpolates every `-f` file *before* merging them.

**On macOS / Docker Desktop, add the dev override:**

```bash
docker compose -f docker-compose.docker.yml -f docker-compose.dev.yml up --build
```

It runs as root (the in-VM socket is `root:root`, so no host gid helps) and
swaps `network_mode: host` for bridge networking plus
`--connect tcp/host.docker.internal:7447`. Docker Desktop's host networking
joins the *Linux VM's* namespace, not the Mac's, so a router published on the
Mac is not at `127.0.0.1` from in there — the container starts, serves nothing
reachable, and looks perfectly healthy in its own logs.

### Healthcheck

The image carries a `HEALTHCHECK` that runs `container-control-healthcheck` —
the same `ping()` the process runs at startup, in a separate entry point that
imports neither zenoh nor argparse. It exists for one failure the startup gate
cannot catch: a socket that goes away *after* boot (a daemon restart, a changed
docker gid, a revoked mount). In that state the process keeps serving, every
RPC returns `UNAVAILABLE`, and without the probe `docker ps` still says the
container is healthy.

```bash
docker inspect --format '{{json .State.Health}}' keelson-interface-docker
```

**This is visibility, not recovery.** `restart: unless-stopped` reacts to a
container *exiting*, not to it going unhealthy — nothing here auto-heals. That
is deliberate: restarting a responder does not fix a socket that is not there,
and keelson's protocol specification names container health checks as the
out-of-band visibility channel, not a control loop.

**`init: true` is not optional.** A process running as PID 1 with no signal
handler installed does not get the default action, so without it `docker stop`
waits out the full grace period and then SIGKILLs — leaving this responder's
liveliness tokens standing until their lease expires.

**The socket mount no longer carries `:ro`.** It used to. That was theatre: the
Engine API is POST-over-HTTP on that socket, and a read-only inode does not make
`POST /containers/{id}/stop` fail. It read as a safeguard while providing none.

### CLI

`--log-level`, `--mode`, `--connect` and `--listen` come from
`keelson.scaffolding`; `-r/--realm`, `-e/--entity-id` and `-s/--source-id` are
required. Beyond those:

| Flag | Default | Meaning |
|---|---|---|
| `--allow-control` | off | Permit start/stop/restart. Requires ≥1 `--allow`. |
| `--allow GLOB` | — | Container name glob that may be controlled; repeatable. |
| `--self-container-name NAME` | — | This responder's own `container_name:`. |
| `--stop-timeout-s` | 10 | Grace period before SIGKILL when a request omits one. |
| `--default-tail-lines` | 200 | Used when a request asks for 0 lines. |
| `--max-tail-lines` | 5000 | Requests above this are clamped, not rejected. |
| `--max-log-bytes` | 1000000 | Oldest lines are dropped to fit; `truncated` is set. |

## Calling it

`container-control-cli` ships in the same image and package:

```bash
container-control-cli -r rise -e masslab -s masslab-4 \
  --mode client --connect tcp/127.0.0.1:7447 list

container-control-cli ... list --running-only --name-glob 'keelson-*'
container-control-cli ... logs --name keelson-router --tail 50 --stream stderr
container-control-cli ... restart --name mcap-recorder
container-control-cli ... stop --name mcap-recorder --timeout-s 5
```

From Python, build the key with `keelson.construct_rpc_key` and do a raw
`session.get`:

```python
import keelson, zenoh
from keelson_interface_docker.interfaces import ListContainersRequest, ListContainersResponse

with zenoh.open(zenoh.Config()) as session:
    key = keelson.construct_rpc_key("rise", "masslab", "container_control", "v1", "list", "masslab-4")
    for reply in session.get(key, payload=ListContainersRequest().SerializeToString(), timeout=5.0):
        print(ListContainersResponse.FromString(reply.ok.payload.to_bytes()))
```

`keelson.interfaces.invoke_procedure()` does **not** work for this interface: it
looks the interface up in the SDK's registry and raises `KeyError` for one
keelson does not ship. That is fixed by upstreaming, below.

## Development

```bash
uv venv && uv pip install -e ".[dev,proto]"
pytest                    # unit tests
RUN_E2E=1 pytest          # + two real Zenoh sessions over loopback
ruff check src/ tests/ && ruff format --check src/ tests/
bash scripts/generate_protos.sh    # after editing the .proto
docker build -t keelson-interface-docker:dev .
```

Test files mirror `src/` one-to-one (`test_backend.py` ↔ `backend.py`), rather
than following keelson's `connectors/CLAUDE.md` `test_*_cli.py` / `test_*_e2e.py`
layout. That convention exists because connectors are `bin/*.py` scripts with no
importable modules to mirror; this repo ships an installable package, so
mirroring the modules is the stronger rule. The subprocess tests satisfy both.

`tests/fake_engine.py` stubs the Docker Engine's `/_ping`, `/version` and
`/containers/json` over a unix socket, so the subprocess tests drive a real
`keelson-interface-docker` process — argparse, zenoh session, `serve_rpc`,
SIGTERM handling — on a machine with no Docker daemon, and in CI.

The generated `*_pb2.py` are **committed**, because nothing regenerates them
between this repo and its container image. CI regenerates and `git diff
--exit-code`s them, so they cannot drift from the `.proto`.

### Releasing

Tags are bare `X.Y.Z` / `X.Y.Z-pre.N`, matching the rest of the fleet
(`ghcr.io/rise-maritime/keelson:0.6.0-pre.13`) — no `v` prefix.

**The tag is the version.** The release workflow writes it into
`pyproject.toml` with `uv version --frozen` before building, and `__init__.py`
reads it back out of the installed metadata at runtime, so the tag you pull and
the version the process reports cannot disagree. Do not hand-bump the version in
`pyproject.toml`; it is a placeholder and is labelled as one.

The two spellings differ on purpose. `uv` normalises to PEP 440, so a tag of
`0.1.0-pre.2` gives a *package* version of `0.1.0rc2` while the *image* stays
tagged `0.1.0-pre.2` — that one comes straight from the tag. Checking both:

```bash
docker run --rm --entrypoint python \
  ghcr.io/rise-maritime/keelson-interface-docker:0.1.0-pre.2 \
  -c "import keelson_interface_docker as k; print(k.__version__)"    # 0.1.0rc2
```

A release builds from the tagged commit, so a failed release cannot be fixed by
re-running the workflow — the fix has to be merged and a new tag cut.

## Capturing logs to MCAP

The `logs` procedure answers a question asked now. `--follow-logs` answers the
one asked later — it follows matching containers continuously and publishes each
line on keelson's well-known `log_message` subject as a `foxglove.Log`, so the
fleet's MCAP recorder captures it alongside everything else on the bus. That is
the only way anyone reads the logs of a container that has already died on a
machine they cannot reach.

```
--follow-logs 'keelson-*' --follow-logs 'mcap-*'
```

**Independent of `--allow-control` by design.** Recording a container's output
and being allowed to restart it are different decisions, and this responder is
read-only in every deployment — gating capture on the control allow-list would
have meant capturing nothing, everywhere.

**One channel per container.** The key carries the container name:

```
{realm}/@v0/{entity}/pubsub/log_message/{source_id}/{container}
```

The recorder makes one MCAP channel per full key, so each container is a
separate togglable channel in Foxglove rather than one merged firehose. Because
`log_message` is a well-known subject the recorder writes a real protobuf
schema (`foxglove.Log`), which is what Foxglove Studio's Log panel binds to — an
ad-hoc subject name would record as an undecodable blob instead.

| Flag | Default | Meaning |
|---|---|---|
| `--follow-logs GLOB` | — | Container name glob to follow; repeatable. Off entirely when unset. |
| `--follow-rescan-s` | 10 | How often to look for containers that have appeared or gone. |
| `--follow-max-lines-per-s` | 200 | Per-container ceiling; see below. |
| `--follow-queue-size` | 10000 | Lines buffered before the oldest are dropped. |
| `--follow-tail` | 0 | History replayed when a follow starts. 0 starts at the end. |

**Overload degrades; it does not take the responder down.** A crash-looping
container can emit megabytes a second. Above the rate cap lines are dropped and
a single `[keelson] dropped N lines` entry is published in their place, so the
gap is visible in the recording rather than silent. If the publish queue backs
up, the oldest entries go. Both are deliberate: this process's primary job is
answering `list` / `start` / `stop`, and losing that because one container is
noisy would be a self-inflicted outage. (The MCAP recorder makes the opposite
choice and exits when it cannot keep up — right for a recorder, wrong here.)

**Levels are sniffed, and it is a heuristic.** `foxglove.Log.level` drives the
Log panel's colouring, so lines are scanned for a standalone severity token near
the start (`ERROR`, `WARN`, `panic:`, …), defaulting to INFO. Deliberately *not*
stderr→ERROR: plenty of well-behaved programs write everything to stderr because
it is unbuffered, and a solid-red panel teaches the operator to ignore the
colour. The match is anchored on word boundaries so "no errors found" stays INFO.

**Volume is real.** Logs ride the `background` QoS profile (DATA_LOW, DROP), so
locally they yield to live data — but nothing downsamples text upstream the way
the router downsamples images. On a constrained link, narrow the glob.

## Deliberately not done

Three things a reviewer reasonably asks for, and why this responder does not do
them. Each is a decision, not an omission.

### It does not serve `configurable/v1`

Tempting — the allow-list looks like configuration. It would be a hole straight
through the guard.

`keelson.scaffolding.configurable`'s `set_config` handler is
`set_config_cb(json.loads(op.request_bytes))` and nothing else: no caller
identity, no authorisation, no validation beyond whatever the callback does.
Exposing the allow-list through it would let **any peer that can reach one zenoh
key** POST `{"control_enabled": true, "allow_globs": ["*"]}` and disable every
check in [Safety model](#safety-model) — on a process that is root-equivalent on
its host. The guard's whole value is that it is set at deploy time by whoever
wrote the compose file.

Three lesser reasons, any of which would still count:

- `make_configurable` declares a `configuration_json` publisher unconditionally,
  and does not declare the subject-level liveliness token that publishing a
  subject owes. (This responder does publish — `log_message`, when
  `--follow-logs` is set — and declares that token itself; the objection is
  that `make_configurable` would add a second published subject without one.)
- It republishes the whole config on every set, from a `finally:` — so a
  *rejected* attempt broadcasts the allow-list too.
- keelson's own guidance puts deployment-static mappings in version control and
  reserves RPC configuration for live-editable ones. An allow-list is the
  definition of deployment-static.

Adoption upstream is thin and consistent with that: four entry points across
three of ~21 connectors, every one a live-editable *watch set*, none a security
boundary.

### It does not publish `entity_health`

A connector publishing its own health bakes health *policy* into the connector,
and two emitters writing the same key race and flip-flop. keelson's dedicated
`entity_health` processor is the sanctioned aggregator.

The part that surprises people: **that aggregator cannot see this responder
either.** It subscribes to exact `(source, subject)` pub/sub pairs, and its
liveliness subscription deliberately cannot reach `@rpc` tokens — zenoh treats
`@`-prefixed chunks as verbatim, so no wildcard matches them. Its own source
comment says as much, and calls it intended.

**The health signal is the RPC interface liveliness token** that `serve_rpc`
declares: `{realm}/@v0/{entity}/@rpc/container_control/v1/*/{source}`. Present
means serving. Crowsnest already derives its "is this responder alive?" dot from
exactly that.

### It does not publish container or host stats

Logs were a different case, and the difference is the whole reason one was
done and the other was not: `log_message` → `foxglove.Log` already existed
upstream, with a QoS profile assigned. Resource metrics have no such subject.

`docker stats`-style telemetry (CPU, memory, restart history) is not on the bus,
for three independent reasons:

1. **No subject fits.** The nearest misses in keelson's `subjects.yaml` —
   `sensor_status`, `network_status`, `device_uptime_duration` — are all about a
   *device*. It would need new upstream subjects and payload types.
2. **It could not be a sixth procedure.** Continuous streams are pub/sub, not
   RPC; and adding a procedure to a published interface version is a breaking
   change requiring `v2`, because a consumer cannot tell "this implementor
   predates the method" from "this implementor is unreachable" — zenoh returns
   no reply for both.
3. **The fleet already answers it, off-bus and on purpose.** netdata and
   portainer run per platform. Putting per-container stats on the bus would buy
   a worse version of a deployed tool, on the link that carries navigation data.

## Upstreaming this interface into keelson

`container_control/v1` is served here but is not yet one of keelson's well-known
interfaces, which is why this repo ships a one-line `interfaces/interfaces.yaml`
and registers it at startup with `keelson.add_well_known_interfaces()`.

**Why that matters more than the warning it silences:** both keelson SDKs
generate their interface registries from `messages/interfaces.yaml` alone. Until
the line is there, no JS/TS or Foxglove client can *discover* the interface at
all, Python's `keelson.interfaces.invoke_procedure()` raises `KeyError` for it,
and every consumer has to carry its own copy of the schema — which is why
crowsnest ships `src/proto/containerControl.json` plus a generator, and why two
field-number tables (`tests/test_proto_contract.py` here and
`scripts/checks/containerControl.mjs` there) exist purely to keep the copies
honest.

**Status: prepared.** The keelson change is committed on the branch
`feat/container-control-interface` — `interfaces/ContainerControl.proto`, the
`messages/interfaces.yaml` line, and a procedure-order assertion in
`sdks/python/tests/test_interfaces_registry.py`. Both SDK generators pick it up
unmodified; verified locally that the Python registry resolves all 18 interfaces
and that `ContainerControlDefinition` reaches the JS `serviceRegistry.ts`.

To finish:

1. Push that branch, open the PR, and cut an **alpha** from it
   (`workflow_dispatch` with the PR number publishes `0.6.0-alpha.<pr>.dev.<n>`
   to PyPI *and* npm). That alpha — not a merge, not a release — is what
   unblocks both consumers.
2. Here: point
   [`src/keelson_interface_docker/interfaces/__init__.py`](src/keelson_interface_docker/interfaces/__init__.py)
   at `keelson.interfaces.ContainerControl_pb2`, then delete the local `_pb2`,
   `scripts/generate_protos.sh`, the `proto` extra, `interfaces/`, the
   `proto-drift` CI job, and `INTERFACES_YAML` (imported by `app.py`, `cli.py`
   and `tests/test_proto_contract.py`). Collapse `cli.py` onto
   `invoke_procedure`, which now works. That `__init__.py` is the only import
   site, deliberately: the two copies **cannot** coexist — both register
   `keelson.interfaces.container_control.*` in protobuf's default descriptor
   pool, and the second raises, so a half-finished migration fails loudly at
   import rather than quietly serving two descriptors.
3. In crowsnest-dev, **in one commit** (its `rpcKeys.mjs` check fails the moment
   a provisional entry becomes well-known, which happens on the pin move alone):
   repin `@rise-maritime/keelson-js`, delete the `PROVISIONAL_INTERFACES` entry,
   `src/proto/containerControl.json` and its generator, switch
   `containerControlRpc.js` to the SDK module, and add the deep import to
   `vite.config.ts`'s `optimizeDeps.include`. Watch the timestamps there:
   ts-proto decodes `google.protobuf.Timestamp` to a **`Date`**, where the
   protobufjs descriptor gives `{seconds, nanos}`.

**Order matters:** step 2 deletes the `.proto` that crowsnest's generator reads
from `../../keelson-interface-docker/interfaces/`. Do step 3 first, or both
together — do not leave that window open.

## Migrating from the old interface

Before v1.0.0 this served a single queryable at
`{realm}/{entity}/docker-sdk/{id}/docker/id`, dispatching on zenoh query
parameters (`?logs=`, `?start=`, `?stop=`, `?restart=`) and replying with a
keelson `Envelope` wrapping JSON.

None of that survives, and the old path is deliberately **not** kept alive: a
`?stop=<id>` request has no way to express the allow-list, the read-only default
or self-protection, so serving it would be a hole straight through the guard.

| Then | Now |
|---|---|
| `GET {key}` | `list` procedure |
| `GET {key}?logs=<id>` | `logs` procedure, addressed by **name** |
| `GET {key}?start=<id>` | `start` procedure |
| Envelope-wrapped JSON | Bare serialized protobuf — keelson RPC does not envelope replies |
| `ghcr.io/mo-rise/...` | `ghcr.io/rise-maritime/...` |

The image org changed, so the old `:latest` is frozen and nothing upgrades
silently — every deployment must be repointed by hand. Pin a tag while you are
there.
