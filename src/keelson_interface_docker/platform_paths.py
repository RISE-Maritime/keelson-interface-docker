"""Resolving a caller-supplied path inside the platforms repository.

THIS MODULE IS THE SECURITY BOUNDARY for ``platform_config/v1``. Every path that
reaches the filesystem goes through :func:`resolve`, and nothing else in the
package joins a caller string onto the repository root. It imports neither
``zenoh`` nor ``docker`` nor ``git`` -- it is pure, so it can be tested
exhaustively without any of them.

THE RULE IS "RESOLVE, THEN PROVE IT IS INSIDE", not "reject bad-looking
strings". Blocklisting ``..`` is the classic way to get this wrong: it misses
absolute paths, it misses a symlink whose target is outside, and it misses
encodings nobody thought of. Resolving first collapses every one of those into a
single real path, and one containment check then answers all of them at once.

FOUR THINGS ARE REFUSED, and each is a different attack or accident:

* **Absolute paths.** The caller does not know the responder's root and must not
  be able to address anything by it.
* **Escaping the root**, however expressed -- ``..`` components, or a symlink
  inside the tree pointing out of it.
* **Anything under ``.git``.** Write access there is write access to history:
  ``.git/config`` alone can set ``core.fsmonitor`` or a hook that runs on the
  next command. The repository's *contents* are the editable surface; its
  machinery is not.
* **Extensions outside the allow-list.** This interface exists to edit
  configuration. A responder that will write any filename is one bug away from
  writing ``authorized_keys`` into a bind-mounted home.

REFUSAL HAPPENS BEFORE THE FILESYSTEM IS TOUCHED for the shape checks, so a
rejection cannot be used to probe what exists -- the same property
``guard.py`` maintains by deciding before the container is looked up.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

#: Extensions this interface will read or write.
#:
#: Every one is a configuration format actually present in keelson-platforms:
#: compose and netplan YAML, the platform-geometry and policy JSON, zenoh's
#: JSON5 router configs, the hand-written READMEs, and logrotate.conf.
#:
#: ``.env`` is handled separately below because it is a *name*, not a suffix --
#: ``Path(".env").suffix`` is ``""``, so a suffix-only check silently refuses
#: the five .env files that decide DOCKER_GID and the zenoh realm.
ALLOWED_SUFFIXES = frozenset({".yml", ".yaml", ".json", ".json5", ".md", ".conf"})

#: Exact filenames allowed regardless of suffix.
ALLOWED_NAMES = frozenset({".env"})

#: Path components that are never traversable.
FORBIDDEN_COMPONENTS = frozenset({".git"})


class PathError(ValueError):
    """A caller-supplied path that will not be resolved.

    Carries no filesystem detail on purpose: the message says which *rule*
    refused, never whether the target happens to exist.
    """


def is_allowed_name(name: str) -> bool:
    """True if *name* is a filename this interface will read or write."""
    return name in ALLOWED_NAMES or PurePosixPath(name).suffix.lower() in ALLOWED_SUFFIXES


def _check_shape(relative: str) -> PurePosixPath:
    """Reject on the string alone, before the filesystem is consulted."""
    if not relative or not relative.strip():
        raise PathError("path is empty")

    # A backslash is not a separator on POSIX, so "a\\..\\b" would survive the
    # component check below and then mean something different to a tool that
    # does treat it as one. Refuse rather than guess which is intended.
    if "\\" in relative:
        raise PathError("path contains a backslash")

    if "\x00" in relative:
        raise PathError("path contains a null byte")

    pure = PurePosixPath(relative)

    if pure.is_absolute():
        raise PathError("path must be relative to the repository root")

    for part in pure.parts:
        if part == "..":
            raise PathError("path must not contain '..'")
        if part in FORBIDDEN_COMPONENTS:
            raise PathError(f"path must not traverse '{part}'")

    return pure


def resolve(root: Path, relative: str, *, must_be_file: bool = False) -> Path:
    """Resolve *relative* against *root*, proving the result stays inside.

    :param root: the repository root, as configured by ``--platforms-root``.
    :param relative: a caller-supplied repository-relative path.
    :param must_be_file: also require that the target exists and is a regular
        file. Left False for a write to a path that does not exist yet.
    :raises PathError: if any rule refuses it.
    """
    _check_shape(relative)

    root_real = root.resolve()
    # strict=False: a write may target a file that does not exist yet. The
    # containment check below does not depend on existence -- resolve() still
    # collapses ".." and follows the symlinks that DO exist, which is what
    # matters, because the escape has to happen through an existing directory.
    candidate = (root_real / relative).resolve(strict=False)

    if candidate != root_real and root_real not in candidate.parents:
        # Reached by a symlink inside the tree pointing out of it -- the shape
        # check cannot see that, only resolution can.
        raise PathError("path escapes the repository root")

    if not is_allowed_name(candidate.name):
        raise PathError(
            f"'{candidate.name}' is not an editable configuration file "
            f"(allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}, or .env)"
        )

    if must_be_file and not candidate.is_file():
        raise PathError("no such file")

    return candidate


def relative_to_root(root: Path, path: Path) -> str:
    """The repository-relative, POSIX-separated form of *path*.

    Every path this interface reports travels in this form -- never absolute.
    The responder's root is deployment configuration, and leaking it into a
    response tells a caller about the host's filesystem layout for no benefit.
    """
    return path.resolve().relative_to(root.resolve()).as_posix()


def path_matches(relative: str, pattern: str) -> bool:
    """Segment-aware glob match of a repository-relative path.

    NOT ``fnmatch``, and the difference is the whole reason this exists:
    ``fnmatch``'s ``*`` crosses ``/``, so ``--allow-path 'platforms/sealog-9/*'``
    written by an operator who means "that entity's files" would silently also
    match ``platforms/sealog-9/nested/anything``. An allow-list that is wider
    than it reads is worse than no allow-list, because it is trusted.

    Here ``*`` and ``?`` stay within one segment and ``**`` spans any number of
    them, which is the convention every operator already knows from ``.gitignore``
    and shell globstar:

    * ``platforms/*`` -- the entity directories, not their contents
    * ``platforms/*/*.yml`` -- each entity's compose files, one level deep
    * ``platforms/sealog-9/**`` -- everything under one entity, any depth
    * ``**`` -- the whole repository

    :param relative: a repository-relative POSIX path.
    :param pattern: a glob in the form described above.
    """
    return _match_segments(
        tuple(p for p in PurePosixPath(relative).parts if p),
        tuple(p for p in PurePosixPath(pattern).parts if p),
    )


def _match_segments(path: tuple[str, ...], pat: tuple[str, ...]) -> bool:
    if not pat:
        return not path

    head, rest = pat[0], pat[1:]

    if head == "**":
        # Match zero or more segments: try every split point. Zero first, so
        # "a/**" matches "a" itself as well as everything beneath it.
        if _match_segments(path, rest):
            return True
        return bool(path) and _match_segments(path[1:], pat)

    if not path:
        return False

    return fnmatchcase(path[0], head) and _match_segments(path[1:], rest)
