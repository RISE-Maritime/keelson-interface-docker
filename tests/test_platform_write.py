"""Writing a file: optimistic concurrency and atomicity.

The base_sha256 check is the interesting part. It is what stops two operators —
or one operator and one person at an SSH prompt — from silently overwriting each
other, and it is the path the UI turns into a "reload and re-apply?" dialog
rather than an error.
"""

from pathlib import Path

import pytest

from keelson_interface_docker.platform_repo import RepoError, sha256_of
from keelson_interface_docker.platform_write import atomic_write, check_base_sha

ORIGINAL = b"services:\n  a:\n    image: x\n"
EDITED = b"services:\n  a:\n    image: y\n"


@pytest.fixture
def existing(tmp_path: Path) -> Path:
    p = tmp_path / "docker-compose.a.yml"
    p.write_bytes(ORIGINAL)
    return p


class TestBaseShaGuard:
    def test_matching_sha_is_accepted(self, existing: Path) -> None:
        assert check_base_sha(existing, sha256_of(ORIGINAL)) == ORIGINAL

    def test_a_changed_file_is_refused(self, existing: Path) -> None:
        """The file moved underneath the editor — the whole point of the field."""
        existing.write_bytes(b"someone else got here first\n")
        with pytest.raises(RepoError, match="changed on disk") as exc:
            check_base_sha(existing, sha256_of(ORIGINAL))
        # INVALID_STATE, not IO_FAILURE: the UI turns this specific code into a
        # second confirmation rather than a red banner.
        assert exc.value.code == 9 or "changed on disk" in exc.value.message

    def test_a_deleted_file_is_refused(self, existing: Path) -> None:
        existing.unlink()
        with pytest.raises(RepoError, match="no longer exists"):
            check_base_sha(existing, sha256_of(ORIGINAL))

    def test_empty_sha_creates(self, tmp_path: Path) -> None:
        assert check_base_sha(tmp_path / "new.yml", "") == b""

    def test_empty_sha_refuses_an_existing_file(self, existing: Path) -> None:
        """Empty means "expect absent", NOT "overwrite whatever is there".

        There is deliberately no way to express "I don't care" — an escape hatch
        would be used on the day it mattered.
        """
        with pytest.raises(RepoError, match="already exists"):
            check_base_sha(existing, "")


class TestAtomicWrite:
    def test_replaces_content(self, existing: Path) -> None:
        atomic_write(existing, EDITED)
        assert existing.read_bytes() == EDITED

    def test_creates_a_new_file(self, tmp_path: Path) -> None:
        target = tmp_path / "docker-compose.new.yml"
        atomic_write(target, EDITED)
        assert target.read_bytes() == EDITED

    def test_bytes_are_preserved_exactly(self, existing: Path) -> None:
        """No transcoding, no line-ending fixup, no trailing-newline helpfulness.

        An editor that opens and saves must not produce a diff nobody asked for,
        and a latin-1 byte in a comment about a sensor angle must survive.
        """
        awkward = b"# angle: 45\xb0\r\nservices:\n  a:\n    image: x"
        atomic_write(existing, awkward)
        assert existing.read_bytes() == awkward

    def test_leaves_no_temporary_files(self, existing: Path) -> None:
        atomic_write(existing, EDITED)
        assert [p.name for p in existing.parent.iterdir()] == [existing.name]

    def test_preserves_mode(self, existing: Path) -> None:
        existing.chmod(0o640)
        atomic_write(existing, EDITED)
        assert existing.stat().st_mode & 0o777 == 0o640

    def test_a_missing_directory_is_not_created(self, tmp_path: Path) -> None:
        """This interface edits an entity's config; it does not create entities."""
        with pytest.raises(RepoError, match="no such directory"):
            atomic_write(tmp_path / "nonexistent" / "a.yml", EDITED)
