"""The four gates for platform_config/v1.

The invariant these tests exist to protect is that the gates are INDEPENDENT.
The ordinary deployment is write on, delete off, git on, push off, so a
implementation that derived any gate from another would be wrong in the common
case rather than in an exotic one — and the contract tests on both sides of the
wire assert the same thing at the field level.

The contexts below are deliberately graded, with the delete list NARROWER than
the write list, so a test cannot pass vacuously by having both allow everything.
"""

import pytest

from keelson_interface_docker.platform_guard import FileGuard
from keelson_interface_docker.platform_paths import path_matches

SEALOG = "platforms/sealog-9/docker-compose.rec-mcap.yml"
GOTA = "platforms/gota/docker-compose.ais.yml"
SCRATCH = "platforms/dev/docker-compose.atak.yml"


@pytest.fixture
def readonly() -> FileGuard:
    return FileGuard()


@pytest.fixture
def writable() -> FileGuard:
    """The ordinary deployment: edit anything, delete nothing, commit, no push."""
    return FileGuard(
        write_enabled=True,
        write_globs=("platforms/**",),
        git_enabled=True,
    )


@pytest.fixture
def deletable() -> FileGuard:
    """Delete allowed, but only in the scratch entity — narrower than write."""
    return FileGuard(
        write_enabled=True,
        write_globs=("platforms/**",),
        delete_globs=("platforms/dev/**",),
        git_enabled=True,
        push_enabled=True,
    )


class TestDefaultIsReadOnly:
    def test_write_refused(self, readonly: FileGuard) -> None:
        d = readonly.decide_write(SEALOG)
        assert not d.allowed
        assert "--allow-write" in d.reason

    def test_delete_refused(self, readonly: FileGuard) -> None:
        assert not readonly.decide_delete(SEALOG).allowed

    def test_flags_report_false(self, readonly: FileGuard) -> None:
        assert readonly.write_enabled is False
        assert readonly.delete_enabled is False
        assert readonly.git_enabled is False
        assert readonly.push_enabled is False

    def test_the_reason_names_the_fix(self, readonly: FileGuard) -> None:
        """An operator reading the refusal must learn what to do about it."""
        assert "--allow-path" in readonly.decide_write(SEALOG).reason


class TestWriteAllowList:
    def test_a_path_inside_the_list(self, writable: FileGuard) -> None:
        assert writable.decide_write(SEALOG).allowed

    def test_a_path_outside_the_list(self) -> None:
        guard = FileGuard(write_enabled=True, write_globs=("platforms/sealog-9/**",))
        d = guard.decide_write(GOTA)
        assert not d.allowed
        assert "allow-list" in d.reason
        assert "platforms/sealog-9/**" in d.reason

    def test_the_glob_does_not_silently_cross_directories(self) -> None:
        """`*` stays in one segment — the fnmatch footgun this guard avoids.

        An operator writing `platforms/sealog-9/*` means that entity's files. If
        `*` crossed `/`, the list would be quietly wider than it reads, and a
        wider-than-it-reads allow-list is worse than none because it is trusted.
        """
        guard = FileGuard(write_enabled=True, write_globs=("platforms/sealog-9/*",))
        assert guard.decide_write(SEALOG).allowed
        assert not guard.decide_write("platforms/sealog-9/extra/nested.yml").allowed


class TestDeleteIsGatedSeparately:
    """The gate whose mistake is unrecoverable."""

    def test_write_does_not_imply_delete(self, writable: FileGuard) -> None:
        """The ordinary deployment: everything writable, nothing deletable."""
        assert writable.decide_write(SEALOG).allowed
        d = writable.decide_delete(SEALOG)
        assert not d.allowed
        assert "--allow-delete" in d.reason
        assert "enabling" in d.reason and "does not enable it" in d.reason

    def test_delete_enabled_is_false_without_a_list(self, writable: FileGuard) -> None:
        assert writable.write_enabled is True
        assert writable.delete_enabled is False

    def test_delete_list_may_be_narrower_than_write(self, deletable: FileGuard) -> None:
        """ "Edit every entity, delete only in dev" must be expressible."""
        assert deletable.decide_write(SEALOG).allowed
        assert not deletable.decide_delete(SEALOG).allowed
        assert deletable.decide_write(SCRATCH).allowed
        assert deletable.decide_delete(SCRATCH).allowed

    def test_delete_needs_write_too(self) -> None:
        """A delete list alone does not open a door that write is holding shut."""
        guard = FileGuard(write_enabled=False, delete_globs=("**",))
        assert not guard.decide_delete(SEALOG).allowed
        assert guard.delete_enabled is False


class TestGitAndPushAreSeparate:
    def test_write_without_git(self) -> None:
        """Edits land in the working tree; nothing is committed."""
        guard = FileGuard(write_enabled=True, write_globs=("**",))
        assert guard.decide_write(SEALOG).allowed
        assert guard.git_enabled is False
        assert guard.push_enabled is False

    def test_git_without_push(self, writable: FileGuard) -> None:
        """The safe middle: commits are inspectable locally before publishing.

        This is the state the first end-to-end run should be in — enabling
        committing must not silently also publish to the repository every other
        platform pulls from.
        """
        assert writable.git_enabled is True
        assert writable.push_enabled is False

    def test_all_four_can_be_on(self, deletable: FileGuard) -> None:
        assert (
            deletable.write_enabled,
            deletable.delete_enabled,
            deletable.git_enabled,
            deletable.push_enabled,
        ) == (True, True, True, True)


class TestReportedFlagsMatchTheAnswer:
    """A greyed button must agree with what the call would actually do."""

    def test_writable_tracks_decide_write(self, deletable: FileGuard) -> None:
        for path in (SEALOG, GOTA, SCRATCH, "platforms/../outside.yml"):
            assert deletable.writable(path) == deletable.decide_write(path).allowed

    def test_deletable_tracks_decide_delete(self, deletable: FileGuard) -> None:
        for path in (SEALOG, GOTA, SCRATCH):
            assert deletable.deletable(path) == deletable.decide_delete(path).allowed

    def test_writable_and_deletable_disagree_in_the_normal_case(self, writable: FileGuard) -> None:
        """If these two ever agree everywhere, the separation has been lost."""
        assert writable.writable(SEALOG) is True
        assert writable.deletable(SEALOG) is False


class TestPathMatching:
    """The matcher the allow-lists are built on."""

    @pytest.mark.parametrize(
        ("relative", "pattern", "want"),
        [
            ("platforms/sealog-9/a.yml", "platforms/sealog-9/*", True),
            ("platforms/sealog-9/deep/a.yml", "platforms/sealog-9/*", False),
            ("platforms/sealog-9/deep/a.yml", "platforms/sealog-9/**", True),
            ("platforms/sealog-9", "platforms/sealog-9/**", True),
            ("platforms/gota/a.yml", "platforms/*/*.yml", True),
            ("platforms/gota/a.json", "platforms/*/*.yml", False),
            ("anything/at/all.yml", "**", True),
            ("platforms/stena/a.yml", "platforms/sealog-9/**", False),
            ("platforms/sealog-9/a.yml", "platforms/sealog-1?/*", False),
            ("platforms/sealog-9/a.yml", "platforms/sealog-?/*", True),
        ],
    )
    def test_segment_aware(self, relative: str, pattern: str, want: bool) -> None:
        assert path_matches(relative, pattern) is want
