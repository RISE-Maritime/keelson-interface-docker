"""Reading the platforms repository.

The interesting assertions here are all about ABSENCE VERSUS ZERO, which is the
distinction ``optional uint32 service_count`` exists to carry and the one a
naive implementation collapses.
"""

from pathlib import Path

import pytest

from keelson_interface_docker.platform_repo import count_services, has_readme


@pytest.fixture
def entity(tmp_path: Path) -> Path:
    d = tmp_path / "sealog-9"
    d.mkdir()
    return d


def _write(d: Path, name: str, text: str) -> Path:
    p = d / name
    p.write_text(text)
    return p


GOOD = "services:\n  a:\n    image: x\n  b:\n    image: y\n"
ALSO_GOOD = "services:\n  c:\n    image: z\n"

# Verbatim in shape from platforms/landkrabb/docker-compose.radar-aptiv.yml,
# which `docker compose config` also refuses.
DUPLICATE_KEY = "services:\n  radar:\n    image: x\n  radar:\n    image: y\n"


class TestServiceCount:
    def test_counts_across_files(self, entity: Path) -> None:
        paths = [
            _write(entity, "docker-compose.a.yml", GOOD),
            _write(entity, "docker-compose.b.yml", ALSO_GOOD),
        ]
        assert count_services(paths) == 3

    def test_no_compose_files_is_a_confident_zero(self, entity: Path) -> None:
        """A directory holding only a guide genuinely defines no services.

        Dashing this would understate what is known — iotas is exactly this
        case in the real repository.
        """
        paths = [_write(entity, "HW_GUIDE.md", "# hardware\n")]
        assert count_services(paths) == 0

    def test_an_unparseable_file_makes_the_total_unknowable(self, entity: Path) -> None:
        """None, not a partial sum.

        The other files parsed, but their sum is NOT the directory's total, and
        reporting it as though it were is the confident wrong answer the whole
        presence mechanism exists to prevent.
        """
        paths = [
            _write(entity, "docker-compose.a.yml", GOOD),
            _write(entity, "docker-compose.radar.yml", DUPLICATE_KEY),
        ]
        assert count_services(paths) is None

    def test_a_compose_file_with_no_services_block(self, entity: Path) -> None:
        paths = [_write(entity, "docker-compose.a.yml", "volumes:\n  data: {}\n")]
        assert count_services(paths) == 0

    def test_non_compose_yaml_is_not_counted(self, entity: Path) -> None:
        """netplan-*.yaml is YAML, and is not a compose file."""
        paths = [
            _write(entity, "docker-compose.a.yml", GOOD),
            _write(entity, "netplan-host.yaml", "network:\n  version: 2\n"),
        ]
        assert count_services(paths) == 2


class TestHasReadme:
    def test_finds_markdown(self, entity: Path) -> None:
        assert has_readme([_write(entity, "README.md", "#\n")])

    def test_any_markdown_counts(self, entity: Path) -> None:
        """SYSTEM_MANUAL.md and HW_GUIDE.md are the README in several entities."""
        assert has_readme([_write(entity, "SYSTEM_MANUAL.md", "#\n")])

    def test_none_when_absent(self, entity: Path) -> None:
        assert not has_readme([_write(entity, "docker-compose.a.yml", GOOD)])


class TestParserAgreesWithDockerCompose:
    """The parser must refuse what compose refuses — and accept what it accepts.

    Both directions matter. Accepting a file compose rejects reports a confident
    service count for something that cannot start; refusing a file compose
    accepts dashes a directory that is perfectly fine. The second is the bug
    that shipped first.
    """

    def test_merge_keys_are_accepted(self, entity: Path) -> None:
        """`<<: *anchor` is valid compose and appears in the real repository.

        A strict loader that overrides the mapping constructor loses PyYAML's
        merge handling unless it flattens first — which refused
        landkrabb-small/docker-compose.cam-frame.yml, a file that deploys.
        """
        merged = (
            "x-common: &cam\n"
            "  image: ghcr.io/rise-maritime/keelson-connector-camera:0.3.0\n"
            "  network_mode: host\n"
            "services:\n"
            "  cam-1:\n"
            "    <<: *cam\n"
            "    container_name: cam-1\n"
            "  cam-2:\n"
            "    <<: *cam\n"
            "    container_name: cam-2\n"
        )
        assert count_services([_write(entity, "docker-compose.cam.yml", merged)]) == 2

    def test_duplicate_keys_are_refused(self, entity: Path) -> None:
        """PyYAML silently keeps the last; compose refuses the file outright."""
        assert count_services([_write(entity, "docker-compose.dup.yml", DUPLICATE_KEY)]) is None

    def test_plain_anchors_still_work(self, entity: Path) -> None:
        anchored = "services:\n  a: &svc\n    image: x\n  b: *svc\n"
        assert count_services([_write(entity, "docker-compose.anchor.yml", anchored)]) == 2

    def test_a_merge_may_supply_a_key_the_service_also_sets(self, entity: Path) -> None:
        """Overriding an inherited key is what `<<` is FOR, not a duplicate.

        Checking for duplicates after flattening sees the inherited key beside
        the explicit one and refuses a file that deploys —
        landkrabb-small/docker-compose.cam-frame.yml is exactly this shape.
        """
        overriding = (
            "services:\n"
            "  a: &cam\n"
            "    image: x\n"
            "    container_name: camera-1\n"
            "  b:\n"
            "    container_name: camera-2\n"
            "    <<: *cam\n"
        )
        assert count_services([_write(entity, "docker-compose.cam.yml", overriding)]) == 2
