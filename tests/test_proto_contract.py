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
