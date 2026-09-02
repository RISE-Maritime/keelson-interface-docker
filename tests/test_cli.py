"""The ops client's rendering, including the reply shapes it does not control."""

from keelson.interfaces.ErrorResponse_pb2 import ErrorResponse

from keelson_interface_docker.cli import describe_error
from keelson_interface_docker.interfaces import ContainerInfo


def test_a_typed_error_is_named_by_its_code():
    raw = ErrorResponse(
        error_description="not in the allow-list", code=ErrorResponse.Code.PERMISSION_DENIED
    ).SerializeToString()
    assert describe_error(raw) == "ERROR PERMISSION_DENIED: not in the allow-list"


def test_a_transport_error_is_reported_not_parsed_as_protobuf():
    # A timeout or a missing route produces a zenoh-level ReplyError carrying a
    # plain string. Parsing that as an ErrorResponse raises DecodeError and
    # buries the real problem under a traceback.
    assert "timeout" in describe_error(b"query timeout: no reply")
    assert describe_error(b"query timeout: no reply").startswith("ERROR (transport)")


def test_undecodable_bytes_do_not_raise():
    assert describe_error(b"\xff\xfe\x00 garbage").startswith("ERROR")


def test_a_valid_error_response_is_preferred_over_the_text_fallback():
    raw = ErrorResponse(error_description="", code=ErrorResponse.Code.NOT_FOUND).SerializeToString()
    assert describe_error(raw).startswith("ERROR NOT_FOUND")


def test_unset_timestamps_render_as_a_dash():
    from keelson_interface_docker.cli import _fmt_time

    assert _fmt_time(ContainerInfo(), "started_at") == "-"


def test_set_timestamps_render_as_a_datetime():
    from keelson_interface_docker.cli import _fmt_time

    info = ContainerInfo()
    info.started_at.FromJsonString("2026-01-02T03:04:05Z")
    assert _fmt_time(info, "started_at") == "2026-01-02 03:04:05"
