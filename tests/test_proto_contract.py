"""The wire contract, pinned.

`container_control/v1` lives in no shared SDK: this repo generates the Python
bindings and crowsnest-dev generates the JavaScript ones from the same .proto.
Nothing but a matching pair of assertions keeps the two in step, so the field
numbers are pinned HERE and in crowsnest's scripts/checks/containerControl.mjs.
Changing either table without the other is the bug this file exists to catch.
"""

import keelson
import pytest

from keelson_interface_docker.app import INTERFACES_YAML
from keelson_interface_docker.interfaces import (
    INTERFACE,
    VERSION,
    ContainerInfo,
    ContainerState,
    GetLogsResponse,
    ListContainersResponse,
    LogLine,
)
from keelson_interface_docker.interfaces.ContainerControl_pb2 import DESCRIPTOR

# serve_rpc advertises the COMPLETE interface through one liveliness token, so a
# procedure declared here without a handler would be advertised and never answer.
# tests/test_handlers.py asserts the other half of this equality.
PROCEDURES = ["list", "logs", "start", "stop", "restart"]

CONTAINER_INFO_FIELDS = {
    "name": 1,
    "id": 2,
    "image": 3,
    "state": 4,
    "raw_state": 5,
    "created_at": 6,
    "started_at": 7,
    "finished_at": 8,
    "exit_code": 9,
    "restart_policy": 10,
    "restart_policy_max_retries": 11,
    "restart_count": 12,
    "health": 13,
    "controllable": 14,
    "compose_project": 15,
    "compose_service": 16,
}


def field_numbers(message_cls) -> dict[str, int]:
    return {f.name: f.number for f in message_cls.DESCRIPTOR.fields}


def test_the_service_declares_exactly_the_five_procedures_in_order():
    service = DESCRIPTOR.services_by_name["ContainerControl"]
    assert [m.name for m in service.methods] == PROCEDURES


def test_container_info_field_numbers_are_pinned():
    assert field_numbers(ContainerInfo) == CONTAINER_INFO_FIELDS


def test_response_field_numbers_are_pinned():
    assert field_numbers(ListContainersResponse) == {
        "containers": 1,
        "observed_at": 2,
        "control_enabled": 3,
    }
    assert field_numbers(GetLogsResponse) == {
        "name": 1,
        "id": 2,
        "lines": 3,
        "truncated": 4,
        "tail_lines": 5,
    }
    assert field_numbers(LogLine) == {"time": 1, "stream": 2, "text": 3}


def test_the_package_name_is_the_one_keelson_will_adopt():
    # Upstreaming is a `cp` into keelson/interfaces/; the package must already
    # match the convention its siblings use.
    assert DESCRIPTOR.package == "keelson.interfaces.container_control"


def test_exit_code_is_optional_so_zero_is_distinguishable_from_absent():
    assert ContainerInfo.DESCRIPTOR.fields_by_name["exit_code"].has_presence


def test_enum_zero_values_are_unspecified():
    # proto3 hands back the zero value for an absent field; it must not name a
    # real state.
    assert ContainerState.Name(0) == "CONTAINER_STATE_UNSPECIFIED"


class TestInterfaceRegistration:
    def test_the_shipped_yaml_names_this_service(self):
        keelson.add_well_known_interfaces(INTERFACES_YAML)
        assert keelson.is_interface_well_known(f"{INTERFACE}/{VERSION}")
        assert (
            keelson.get_interface_service(f"{INTERFACE}/{VERSION}")
            == f"{DESCRIPTOR.package}.ContainerControl"
        )

    @pytest.mark.parametrize("procedure", PROCEDURES)
    def test_the_rpc_key_has_the_shape_the_consumer_builds(self, procedure):
        keelson.add_well_known_interfaces(INTERFACES_YAML)
        assert (
            keelson.construct_rpc_key("rise", "masslab", INTERFACE, VERSION, procedure, "masslab-4")
            == f"rise/@v0/masslab/@rpc/container_control/v1/{procedure}/masslab-4"
        )


class TestPublishedState:
    """The published half. Pinned for the same reason the RPC half is: two
    implementations, no shared SDK, and only these numbers holding them
    together."""

    def test_container_host_status_field_numbers_are_pinned(self):
        from keelson_interface_docker.interfaces.ContainerControl_pb2 import (
            ContainerHostStatus,
        )

        assert field_numbers(ContainerHostStatus) == {
            "containers": 1,
            "observed_at": 2,
            "control_enabled": 3,
            "trigger": 4,
            "sequence": 5,
        }

    def test_the_first_three_numbers_match_the_rpc_response(self):
        # Not a coincidence to be tidied away later: the two carry the same three
        # things, and a reader diffing them should see them line up.
        from keelson_interface_docker.interfaces.ContainerControl_pb2 import (
            ContainerHostStatus,
        )

        published = field_numbers(ContainerHostStatus)
        answered = field_numbers(ListContainersResponse)
        for name in ("containers", "observed_at", "control_enabled"):
            assert published[name] == answered[name]

    def test_status_trigger_distinguishes_a_change_from_a_keep_alive(self):
        from keelson_interface_docker.interfaces.ContainerControl_pb2 import StatusTrigger

        assert StatusTrigger.Name(0) == "STATUS_TRIGGER_UNSPECIFIED"
        assert StatusTrigger.Value("STATUS_TRIGGER_CHANGE") == 1
        assert StatusTrigger.Value("STATUS_TRIGGER_HEARTBEAT") == 2

    def test_adding_it_did_not_add_a_sixth_procedure(self):
        # The README rules out a sixth procedure as a v2-requiring break. A
        # published message is not one, and this is what says so.
        service = DESCRIPTOR.services_by_name["ContainerControl"]
        assert [m.name for m in service.methods] == PROCEDURES


class TestSubjectRegistration:
    def test_the_shipped_yaml_names_this_payload(self):
        from keelson_interface_docker.app import PROTO_DESCRIPTOR_SET, SUBJECTS_YAML

        keelson.add_well_known_subjects_and_proto_definitions(
            SUBJECTS_YAML, PROTO_DESCRIPTOR_SET
        )
        assert keelson.is_subject_well_known("container_status")
        assert (
            keelson.get_subject_schema("container_status")
            == f"{DESCRIPTOR.package}.ContainerHostStatus"
        )

    def test_the_pubsub_key_is_one_per_host(self):
        from keelson_interface_docker.app import PROTO_DESCRIPTOR_SET, SUBJECTS_YAML

        keelson.add_well_known_subjects_and_proto_definitions(
            SUBJECTS_YAML, PROTO_DESCRIPTOR_SET
        )
        # No trailing container chunk -- unlike log_message, which is one key per
        # container. See ContainerHostStatus's comment for why removal is the
        # reason.
        assert (
            keelson.construct_pubsub_key("rise", "crab", "container_status", "big")
            == "rise/@v0/crab/pubsub/container_status/big"
        )

    def test_the_descriptor_set_can_actually_decode_the_payload(self):
        # The registry builds a FRESH DescriptorPool, so the descriptor set must
        # embed google/protobuf/timestamp.proto (protoc --include_imports).
        # Without it this raises rather than returning a message.
        from keelson_interface_docker.app import PROTO_DESCRIPTOR_SET, SUBJECTS_YAML
        from keelson_interface_docker.interfaces.ContainerControl_pb2 import (
            ContainerHostStatus,
        )

        keelson.add_well_known_subjects_and_proto_definitions(
            SUBJECTS_YAML, PROTO_DESCRIPTOR_SET
        )
        msg = ContainerHostStatus(control_enabled=True, sequence=3)
        msg.observed_at.FromNanoseconds(1_700_000_000_000_000_000)
        msg.containers.add(name="nginx")

        decoded = keelson.decode_protobuf_payload_from_type_name(
            msg.SerializeToString(), f"{DESCRIPTOR.package}.ContainerHostStatus"
        )
        assert decoded.containers[0].name == "nginx"
        assert decoded.sequence == 3
        assert decoded.HasField("observed_at")


class TestRegistriesShipInsideThePackage:
    """package-data omissions are invisible in a dev checkout, where
    interfaces/ still exists at the repo root, and a startup FileNotFoundError
    in the image."""

    def test_every_registry_file_travels_with_the_package(self):
        from keelson_interface_docker.app import (
            INTERFACES_YAML,
            PROTO_DESCRIPTOR_SET,
            SUBJECTS_YAML,
        )

        for path in (INTERFACES_YAML, SUBJECTS_YAML, PROTO_DESCRIPTOR_SET):
            assert path.exists(), f"{path.name} is missing from the package"
