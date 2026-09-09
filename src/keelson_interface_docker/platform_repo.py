"""Reading the platforms repository: entities, files, and the tree's git state.

The read half of ``platform_config/v1``. Everything here is non-mutating -- it
runs ``git`` only for queries (``rev-parse``, ``status --porcelain``,
``rev-list --count``, ``remote get-url``) and never for anything that changes a
ref, an index or a working tree. The mutating half lives in ``gitops``.

WHY ``git`` AS A SUBPROCESS RATHER THAN A LIBRARY. The repository this serves is
a real checkout that humans also use over SSH, with whatever config, hooks,
credentials and rebase state that implies. A pure-Python reimplementation would
have to agree with the ``git`` those humans run, and would disagree eventually.
Shelling out means there is one implementation of "what does this tree say".

EVERY SUBPROCESS IS PINNED AND TIMED OUT. No shell (``shell=False``, a list
argv), an explicit ``cwd``, an environment scrubbed of anything that could make
git prompt, and a timeout -- a git call that hangs on a credential prompt would
otherwise hold a zenoh queryable thread forever, and the caller would see a
timeout with no idea why.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from .platform_paths import is_allowed_name, relative_to_root

logger = logging.getLogger("keelson-interface-docker.platform")

#: How long any single git query may take.
GIT_TIMEOUT_S = 20.0

#: Largest file this interface will return whole.
#:
#: The biggest configuration file in keelson-platforms is a few kilobytes; a
#: megabyte is far above anything legitimate and far below anything that would
#: strain a zenoh reply. A file over this is returned truncated and flagged, and
#: the contract forbids writing a truncated file back.
MAX_FILE_BYTES = 1_048_576


class RepoError(Exception):
    """A repository operation that could not be completed.

    Carries the ``ErrorResponse.Code`` the caller should see, so a handler can
    translate without re-deciding what went wrong.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def git_env() -> dict[str, str]:
    """Environment for a git subprocess: never interactive, never a prompt.

    ``GIT_TERMINAL_PROMPT=0`` and ``GIT_ASKPASS``/``SSH_ASKPASS`` pointing at
    nothing turn a missing credential into an immediate failure instead of a
    process that waits forever on a tty this daemon does not have. That is the
    difference between "push failed, here is why" and a queryable that never
    answers.
    """
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(Path.home()),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "SSH_ASKPASS": "/bin/false",
        "GIT_CONFIG_NOSYSTEM": "1",
        # Deterministic output regardless of the host's locale.
        "LC_ALL": "C",
    }


def run_git(
    root: Path, *args: str, timeout_s: float = GIT_TIMEOUT_S, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run one git command in *root* and return the completed process.

    :param check: raise :class:`RepoError` on a non-zero exit. Passed False by
        callers that treat failure as data -- ``rev-list`` against a branch with
        no upstream fails, and "no upstream" is an answer, not an error.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            env=git_env(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RepoError(
            ErrorResponse.Code.UNAVAILABLE,
            "git is not installed in this responder's image",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoError(
            ErrorResponse.Code.UNAVAILABLE,
            f"git {args[0] if args else ''} timed out after {timeout_s:g}s",
        ) from exc

    if check and proc.returncode != 0:
        raise RepoError(
            ErrorResponse.Code.IO_FAILURE,
            f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}",
        )
    return proc


@dataclass(frozen=True)
class RepoState:
    """The working tree's position relative to its remote."""

    branch: str
    head_sha: str
    remote_url: str
    ahead: int
    behind: int
    dirty_paths: tuple[str, ...]
    detached: bool


def read_state(root: Path) -> RepoState:
    """Read the tree's branch, head, remote and divergence.

    ``ahead``/``behind`` are measured against the remote-tracking ref as it was
    at the last fetch, NOT against the remote as it is now -- this function does
    no network I/O. The response carries ``last_fetch_at`` beside them so a
    client can say "up to date as of a time" rather than "up to date".
    """
    head_sha = run_git(root, "rev-parse", "HEAD").stdout.strip()

    # --quiet exits non-zero when HEAD is detached, which is a state rather than
    # a failure, so this one is not checked.
    branch_proc = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    detached = branch_proc.returncode != 0
    branch = "" if detached else branch_proc.stdout.strip()

    remote_proc = run_git(root, "remote", "get-url", "origin", check=False)
    remote_url = remote_proc.stdout.strip() if remote_proc.returncode == 0 else ""

    ahead = behind = 0
    if not detached:
        # Fails when the branch has no upstream. That is an answer, not an
        # error: a tree with no upstream is neither ahead nor behind anything.
        counts = run_git(
            root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD", check=False
        )
        if counts.returncode == 0:
            parts = counts.stdout.split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])

    # --porcelain is the stable, parseable form; the human format is explicitly
    # not guaranteed between git versions. -z would be safer for exotic
    # filenames, but the XY status prefix makes the split unambiguous here and
    # these are configuration paths.
    status = run_git(root, "status", "--porcelain", "--untracked-files=all")
    dirty: list[str] = []
    for line in status.stdout.splitlines():
        if len(line) > 3:
            path = line[3:].strip()
            # A rename reads "old -> new"; the new name is what exists now.
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            dirty.append(path.strip('"'))

    return RepoState(
        branch=branch,
        head_sha=head_sha,
        remote_url=remote_url,
        ahead=ahead,
        behind=behind,
        dirty_paths=tuple(sorted(dirty)),
        detached=detached,
    )


def last_fetch_at(root: Path) -> datetime | None:
    """When the tree last fetched, from FETCH_HEAD's mtime.

    None when it never has. Reading the file's mtime rather than asking git is
    deliberate: there is no porcelain for "when did you last fetch", and this is
    what every other tool uses.
    """
    fetch_head = root / ".git" / "FETCH_HEAD"
    try:
        return datetime.fromtimestamp(fetch_head.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def platforms_dir(root: Path) -> Path:
    """The directory whose subdirectories are the entities."""
    return root / "platforms"


def list_entity_names(root: Path) -> list[str]:
    """Every entity directory name, sorted.

    An entity IS a directory name here -- see the .proto. It is deliberately not
    the keelson entity id its compose files pass to ``-e``, because those
    disagree in this repository today and reporting the directory is what makes
    the disagreement visible.
    """
    base = platforms_dir(root)
    if not base.is_dir():
        raise RepoError(
            ErrorResponse.Code.NOT_FOUND,
            "this responder's --platforms-root has no platforms/ directory",
        )
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def list_entity_files(root: Path, entity: str) -> list[Path]:
    """The editable files directly inside one entity directory, sorted.

    Not recursive. The repository nests only rarely (a ``test/`` or ``archive/``
    here and there) and a flat listing is what the directory means to an
    operator; a client that needs more can ask for the nested path directly.
    """
    base = platforms_dir(root) / entity
    if not base.is_dir():
        raise RepoError(ErrorResponse.Code.NOT_FOUND, f"no such entity: {entity!r}")

    return sorted(
        (p for p in base.iterdir() if p.is_file() and is_allowed_name(p.name)),
        key=lambda p: p.name,
    )


def sha256_of(data: bytes) -> str:
    """Lowercase hex SHA-256, the form ``base_sha256`` travels in."""
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: Path) -> tuple[bytes, bool]:
    """Read a file, truncating at :data:`MAX_FILE_BYTES`.

    Returns ``(content, truncated)``. A truncated file must not be written back
    -- the contract makes that a refusal rather than a warning, because saving a
    prefix silently discards the remainder.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RepoError(ErrorResponse.Code.IO_FAILURE, f"could not read: {exc}") from exc

    if len(data) > MAX_FILE_BYTES:
        return data[:MAX_FILE_BYTES], True
    return data, False


def modified_at(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def dirty_set(state: RepoState) -> frozenset[str]:
    """The dirty paths as a set, for per-file and per-entity marking."""
    return frozenset(state.dirty_paths)


def entity_is_dirty(entity_rel: str, dirty: frozenset[str]) -> bool:
    """Whether anything under an entity directory is uncommitted."""
    prefix = f"{entity_rel}/"
    return any(p == entity_rel or p.startswith(prefix) for p in dirty)


class _StrictLoader(yaml.SafeLoader):
    """A YAML loader that refuses duplicate mapping keys, as compose does.

    PyYAML's default silently keeps the LAST of a duplicated key. ``docker
    compose`` does not -- it refuses the file outright ("mapping key ... already
    defined") -- and so does every other YAML implementation in this stack,
    including the one Crowsnest parses with in the browser.

    Accepting what the deployment tool rejects is the worst of both: this
    interface would report a confident service count for a file that cannot
    actually start, and an operator would trust it. One such file exists in
    keelson-platforms today (landkrabb's radar-aptiv compose), which is how this
    was found.
    """


def _no_duplicate_keys(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    # CHECK BEFORE FLATTENING, and skip the merge key itself.
    #
    # A duplicate is something the AUTHOR wrote twice. `<<: *anchor` supplying a
    # key that the service also sets explicitly is not that -- it is the entire
    # point of a merge, and the explicit value wins. Checking after
    # flatten_mapping() sees the inherited key beside the explicit one and calls
    # a correct file malformed: landkrabb-small's cam-frame.yml sets
    # `container_name` explicitly and merges an anchor that also has one.
    seen: set = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        seen.add(key)

    # Resolve `<<` the way PyYAML's own construct_mapping does; without this the
    # merge tag has no constructor and every anchored file is refused.
    loader.flatten_mapping(node)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def parse_compose(text: str):
    """Parse a compose document, refusing what ``docker compose`` would refuse."""
    return yaml.load(text, Loader=_StrictLoader)


def count_services(paths: list[Path]) -> int | None:
    """How many compose services a set of files defines, or None if not knowable.

    None means "I could not produce a total", and that is exactly what the
    wire's ``optional uint32 service_count`` exists to say. It happens when a
    compose file FAILED TO PARSE: the other files in the directory may have
    parsed fine, but their sum is not the directory's total, and reporting a
    partial figure as if it were complete is the confident-wrong-answer this
    field was designed to avoid. One such file exists in keelson-platforms today
    -- landkrabb's radar-aptiv compose has a duplicate mapping key, and
    ``docker compose config`` refuses it too.

    A directory with NO compose files returns 0, not None. That is a real,
    confident answer -- iotas holds only a hardware guide and genuinely defines
    no services -- and dashing it would understate what is known.
    """
    total = 0
    for path in paths:
        if not path.name.startswith("docker-compose"):
            continue
        try:
            doc = parse_compose(path.read_text(encoding="utf-8", errors="replace"))
        except (yaml.YAMLError, OSError):
            return None
        if isinstance(doc, dict) and isinstance(doc.get("services"), dict):
            total += len(doc["services"])

    return total


def has_readme(paths: list[Path]) -> bool:
    return any(p.name.lower().endswith(".md") for p in paths)


def relative(root: Path, path: Path) -> str:
    return relative_to_root(root, path)
