"""The path jail for platform_config/v1.

This is the security boundary, so the tests are adversarial rather than
illustrative: every way out of the root that occurred to me is here, including
the two that a shape check alone cannot catch (an absolute path, and a symlink
inside the tree pointing out of it).

A test that only proves good paths work would pass against a function that
returns its input.
"""

from pathlib import Path

import pytest

from keelson_interface_docker.platform_paths import (
    PathError,
    is_allowed_name,
    relative_to_root,
    resolve,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A miniature platforms repository, shaped like the real one."""
    root = tmp_path / "keelson-platforms"
    (root / "platforms" / "sealog-9").mkdir(parents=True)
    (root / "platforms" / "sealog-9" / "docker-compose.rec-mcap.yml").write_text("services: {}\n")
    (root / "platforms" / "sealog-9" / ".env").write_text("DOCKER_GID=984\n")
    (root / "platforms" / "sealog-9" / "README.md").write_text("# sealog-9\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.yml").write_text("nope\n")
    return root


class TestAcceptsRealPaths:
    """The paths this interface exists to serve."""

    def test_a_compose_file(self, repo: Path) -> None:
        got = resolve(repo, "platforms/sealog-9/docker-compose.rec-mcap.yml", must_be_file=True)
        assert got == repo / "platforms" / "sealog-9" / "docker-compose.rec-mcap.yml"

    def test_a_readme(self, repo: Path) -> None:
        assert resolve(repo, "platforms/sealog-9/README.md", must_be_file=True).name == "README.md"

    def test_dotenv_is_a_name_not_a_suffix(self, repo: Path) -> None:
        """`Path(".env").suffix` is "", so a suffix-only check refuses this.

        Five .env files in the real repository decide DOCKER_GID and the zenoh
        realm; refusing them would make those platforms uneditable.
        """
        assert resolve(repo, "platforms/sealog-9/.env", must_be_file=True).name == ".env"

    def test_a_file_that_does_not_exist_yet(self, repo: Path) -> None:
        """Creating a new config is the point; only must_be_file demands existence."""
        got = resolve(repo, "platforms/sealog-9/docker-compose.new.yml")
        assert got.name == "docker-compose.new.yml"

        with pytest.raises(PathError, match="no such file"):
            resolve(repo, "platforms/sealog-9/docker-compose.new.yml", must_be_file=True)


class TestRefusesEscapes:
    """Every way out of the root, including the ones a shape check cannot see."""

    def test_parent_traversal(self, repo: Path) -> None:
        with pytest.raises(PathError, match=r"\.\."):
            resolve(repo, "platforms/../../outside/secret.yml")

    def test_bare_parent_traversal(self, repo: Path) -> None:
        with pytest.raises(PathError, match=r"\.\."):
            resolve(repo, "../outside/secret.yml")

    def test_absolute_path(self, repo: Path) -> None:
        """The blocklist-shaped bug: no '..' anywhere, and still outside."""
        with pytest.raises(PathError, match="must be relative"):
            resolve(repo, "/etc/passwd")

    def test_absolute_path_to_a_real_file_in_the_repo(self, repo: Path) -> None:
        """Refused even though the target is legitimate -- the FORM is refused.

        Accepting it would mean the responder's root is discoverable by probing.
        """
        inside = str(repo / "platforms" / "sealog-9" / "README.md")
        with pytest.raises(PathError, match="must be relative"):
            resolve(repo, inside)

    def test_symlink_escaping_the_root(self, repo: Path) -> None:
        """Shape is clean; only resolution reveals it leaves the tree."""
        link = repo / "platforms" / "sealog-9" / "escape.yml"
        link.symlink_to(repo.parent / "outside" / "secret.yml")

        with pytest.raises(PathError, match="escapes the repository root"):
            resolve(repo, "platforms/sealog-9/escape.yml")

    def test_symlinked_directory_escaping_the_root(self, repo: Path) -> None:
        link = repo / "platforms" / "elsewhere"
        link.symlink_to(repo.parent / "outside", target_is_directory=True)

        with pytest.raises(PathError, match="escapes the repository root"):
            resolve(repo, "platforms/elsewhere/secret.yml")

    def test_a_symlink_staying_inside_is_fine(self, repo: Path) -> None:
        """The rule is containment, not "no symlinks" -- don't over-refuse."""
        link = repo / "platforms" / "sealog-9" / "alias.yml"
        link.symlink_to(repo / "platforms" / "sealog-9" / "docker-compose.rec-mcap.yml")

        assert resolve(repo, "platforms/sealog-9/alias.yml", must_be_file=True).is_file()


class TestRefusesGitInternals:
    """Write access to .git is write access to history and to hooks."""

    def test_git_config(self, repo: Path) -> None:
        with pytest.raises(PathError, match=r"\.git"):
            resolve(repo, ".git/config")

    def test_nested_git_path(self, repo: Path) -> None:
        """A hook is the sharpest case: writing one gets code run by the next git command."""
        with pytest.raises(PathError, match=r"\.git"):
            resolve(repo, ".git/hooks/pre-commit")

    def test_a_git_path_reached_via_parent_is_refused_too(self, repo: Path) -> None:
        """Refused by the '..' rule, which is checked first — either is correct.

        Asserted on the exception type rather than the message precisely because
        two rules legitimately cover this and pinning which one would make the
        test fail on a harmless reordering.
        """
        with pytest.raises(PathError):
            resolve(repo, "platforms/../.git/hooks/pre-commit")

    def test_refused_before_the_allow_list(self, repo: Path) -> None:
        """A .git path with an allowed suffix is still refused."""
        with pytest.raises(PathError, match=r"\.git"):
            resolve(repo, ".git/description.md")


class TestRefusesNonConfigFiles:
    """This interface edits configuration, not arbitrary files."""

    @pytest.mark.parametrize(
        "name",
        ["authorized_keys", "id_rsa", "run.sh", "photo.jpg", "Dockerfile", "notes.txt"],
    )
    def test_disallowed_names(self, repo: Path, name: str) -> None:
        with pytest.raises(PathError, match="not an editable configuration file"):
            resolve(repo, f"platforms/sealog-9/{name}")

    def test_suffix_matching_is_case_insensitive(self, repo: Path) -> None:
        assert is_allowed_name("Compose.YML")
        assert is_allowed_name("README.MD")

    @pytest.mark.parametrize(
        "name",
        ["a.yml", "a.yaml", "a.json", "a.json5", "a.md", "a.conf", ".env"],
    )
    def test_allowed_names(self, name: str) -> None:
        assert is_allowed_name(name)


class TestRefusesMalformedInput:
    """Shapes that are not paths at all."""

    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_empty(self, repo: Path, bad: str) -> None:
        with pytest.raises(PathError, match="empty"):
            resolve(repo, bad)

    def test_null_byte(self, repo: Path) -> None:
        """Truncation at a NUL is how a checked string and an opened one differ."""
        with pytest.raises(PathError, match="null byte"):
            resolve(repo, "platforms/sealog-9/a.yml\x00.png")

    def test_backslash(self, repo: Path) -> None:
        """Not a separator here, but it is to something downstream."""
        with pytest.raises(PathError, match="backslash"):
            resolve(repo, "platforms\\sealog-9\\a.yml")


class TestReportedPathsAreRelative:
    """The responder's root is deployment detail and never travels in a reply."""

    def test_round_trip(self, repo: Path) -> None:
        rel = "platforms/sealog-9/docker-compose.rec-mcap.yml"
        assert relative_to_root(repo, resolve(repo, rel)) == rel

    def test_never_absolute(self, repo: Path) -> None:
        out = relative_to_root(repo, repo / "platforms" / "sealog-9" / "README.md")
        assert not out.startswith("/")
        assert str(repo) not in out
