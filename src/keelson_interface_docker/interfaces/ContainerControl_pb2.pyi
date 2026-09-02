from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ContainerState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONTAINER_STATE_UNSPECIFIED: _ClassVar[ContainerState]
    CONTAINER_STATE_CREATED: _ClassVar[ContainerState]
    CONTAINER_STATE_RUNNING: _ClassVar[ContainerState]
    CONTAINER_STATE_PAUSED: _ClassVar[ContainerState]
    CONTAINER_STATE_RESTARTING: _ClassVar[ContainerState]
    CONTAINER_STATE_REMOVING: _ClassVar[ContainerState]
    CONTAINER_STATE_EXITED: _ClassVar[ContainerState]
    CONTAINER_STATE_DEAD: _ClassVar[ContainerState]

class RestartPolicy(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESTART_POLICY_UNSPECIFIED: _ClassVar[RestartPolicy]
    RESTART_POLICY_NO: _ClassVar[RestartPolicy]
    RESTART_POLICY_ALWAYS: _ClassVar[RestartPolicy]
    RESTART_POLICY_UNLESS_STOPPED: _ClassVar[RestartPolicy]
    RESTART_POLICY_ON_FAILURE: _ClassVar[RestartPolicy]

class HealthStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HEALTH_STATUS_UNSPECIFIED: _ClassVar[HealthStatus]
    HEALTH_STATUS_NONE: _ClassVar[HealthStatus]
    HEALTH_STATUS_STARTING: _ClassVar[HealthStatus]
    HEALTH_STATUS_HEALTHY: _ClassVar[HealthStatus]
    HEALTH_STATUS_UNHEALTHY: _ClassVar[HealthStatus]

class LogStream(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LOG_STREAM_UNSPECIFIED: _ClassVar[LogStream]
    LOG_STREAM_STDOUT: _ClassVar[LogStream]
    LOG_STREAM_STDERR: _ClassVar[LogStream]

class LogStreamSelector(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LOG_STREAM_SELECTOR_UNSPECIFIED: _ClassVar[LogStreamSelector]
    LOG_STREAM_SELECTOR_STDOUT: _ClassVar[LogStreamSelector]
    LOG_STREAM_SELECTOR_STDERR: _ClassVar[LogStreamSelector]
    LOG_STREAM_SELECTOR_BOTH: _ClassVar[LogStreamSelector]

class StatusTrigger(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STATUS_TRIGGER_UNSPECIFIED: _ClassVar[StatusTrigger]
    STATUS_TRIGGER_CHANGE: _ClassVar[StatusTrigger]
    STATUS_TRIGGER_HEARTBEAT: _ClassVar[StatusTrigger]
CONTAINER_STATE_UNSPECIFIED: ContainerState
CONTAINER_STATE_CREATED: ContainerState
CONTAINER_STATE_RUNNING: ContainerState
CONTAINER_STATE_PAUSED: ContainerState
CONTAINER_STATE_RESTARTING: ContainerState
CONTAINER_STATE_REMOVING: ContainerState
CONTAINER_STATE_EXITED: ContainerState
CONTAINER_STATE_DEAD: ContainerState
RESTART_POLICY_UNSPECIFIED: RestartPolicy
RESTART_POLICY_NO: RestartPolicy
RESTART_POLICY_ALWAYS: RestartPolicy
RESTART_POLICY_UNLESS_STOPPED: RestartPolicy
RESTART_POLICY_ON_FAILURE: RestartPolicy
HEALTH_STATUS_UNSPECIFIED: HealthStatus
HEALTH_STATUS_NONE: HealthStatus
HEALTH_STATUS_STARTING: HealthStatus
HEALTH_STATUS_HEALTHY: HealthStatus
HEALTH_STATUS_UNHEALTHY: HealthStatus
LOG_STREAM_UNSPECIFIED: LogStream
LOG_STREAM_STDOUT: LogStream
LOG_STREAM_STDERR: LogStream
LOG_STREAM_SELECTOR_UNSPECIFIED: LogStreamSelector
LOG_STREAM_SELECTOR_STDOUT: LogStreamSelector
LOG_STREAM_SELECTOR_STDERR: LogStreamSelector
LOG_STREAM_SELECTOR_BOTH: LogStreamSelector
STATUS_TRIGGER_UNSPECIFIED: StatusTrigger
STATUS_TRIGGER_CHANGE: StatusTrigger
STATUS_TRIGGER_HEARTBEAT: StatusTrigger

class ContainerInfo(_message.Message):
    __slots__ = ("name", "id", "image", "state", "raw_state", "created_at", "started_at", "finished_at", "exit_code", "restart_policy", "restart_policy_max_retries", "restart_count", "health", "controllable", "compose_project", "compose_service")
    NAME_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    RAW_STATE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    RESTART_POLICY_FIELD_NUMBER: _ClassVar[int]
    RESTART_POLICY_MAX_RETRIES_FIELD_NUMBER: _ClassVar[int]
    RESTART_COUNT_FIELD_NUMBER: _ClassVar[int]
    HEALTH_FIELD_NUMBER: _ClassVar[int]
    CONTROLLABLE_FIELD_NUMBER: _ClassVar[int]
    COMPOSE_PROJECT_FIELD_NUMBER: _ClassVar[int]
    COMPOSE_SERVICE_FIELD_NUMBER: _ClassVar[int]
    name: str
    id: str
    image: str
    state: ContainerState
    raw_state: str
    created_at: _timestamp_pb2.Timestamp
    started_at: _timestamp_pb2.Timestamp
    finished_at: _timestamp_pb2.Timestamp
    exit_code: int
    restart_policy: RestartPolicy
    restart_policy_max_retries: int
    restart_count: int
    health: HealthStatus
    controllable: bool
    compose_project: str
    compose_service: str
    def __init__(self, name: _Optional[str] = ..., id: _Optional[str] = ..., image: _Optional[str] = ..., state: _Optional[_Union[ContainerState, str]] = ..., raw_state: _Optional[str] = ..., created_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., started_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., finished_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., exit_code: _Optional[int] = ..., restart_policy: _Optional[_Union[RestartPolicy, str]] = ..., restart_policy_max_retries: _Optional[int] = ..., restart_count: _Optional[int] = ..., health: _Optional[_Union[HealthStatus, str]] = ..., controllable: bool = ..., compose_project: _Optional[str] = ..., compose_service: _Optional[str] = ...) -> None: ...

class ListContainersRequest(_message.Message):
    __slots__ = ("running_only", "name_glob")
    RUNNING_ONLY_FIELD_NUMBER: _ClassVar[int]
    NAME_GLOB_FIELD_NUMBER: _ClassVar[int]
    running_only: bool
    name_glob: str
    def __init__(self, running_only: bool = ..., name_glob: _Optional[str] = ...) -> None: ...

class ListContainersResponse(_message.Message):
    __slots__ = ("containers", "observed_at", "control_enabled")
    CONTAINERS_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    CONTROL_ENABLED_FIELD_NUMBER: _ClassVar[int]
    containers: _containers.RepeatedCompositeFieldContainer[ContainerInfo]
    observed_at: _timestamp_pb2.Timestamp
    control_enabled: bool
    def __init__(self, containers: _Optional[_Iterable[_Union[ContainerInfo, _Mapping]]] = ..., observed_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., control_enabled: bool = ...) -> None: ...

class GetLogsRequest(_message.Message):
    __slots__ = ("name", "tail_lines", "since", "stream")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TAIL_LINES_FIELD_NUMBER: _ClassVar[int]
    SINCE_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    name: str
    tail_lines: int
    since: _timestamp_pb2.Timestamp
    stream: LogStreamSelector
    def __init__(self, name: _Optional[str] = ..., tail_lines: _Optional[int] = ..., since: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., stream: _Optional[_Union[LogStreamSelector, str]] = ...) -> None: ...

class LogLine(_message.Message):
    __slots__ = ("time", "stream", "text")
    TIME_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    time: _timestamp_pb2.Timestamp
    stream: LogStream
    text: str
    def __init__(self, time: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., stream: _Optional[_Union[LogStream, str]] = ..., text: _Optional[str] = ...) -> None: ...

class GetLogsResponse(_message.Message):
    __slots__ = ("name", "id", "lines", "truncated", "tail_lines")
    NAME_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    LINES_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    TAIL_LINES_FIELD_NUMBER: _ClassVar[int]
    name: str
    id: str
    lines: _containers.RepeatedCompositeFieldContainer[LogLine]
    truncated: bool
    tail_lines: int
    def __init__(self, name: _Optional[str] = ..., id: _Optional[str] = ..., lines: _Optional[_Iterable[_Union[LogLine, _Mapping]]] = ..., truncated: bool = ..., tail_lines: _Optional[int] = ...) -> None: ...

class StartContainerRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class StopContainerRequest(_message.Message):
    __slots__ = ("name", "timeout_s")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    name: str
    timeout_s: int
    def __init__(self, name: _Optional[str] = ..., timeout_s: _Optional[int] = ...) -> None: ...

class RestartContainerRequest(_message.Message):
    __slots__ = ("name", "timeout_s")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    name: str
    timeout_s: int
    def __init__(self, name: _Optional[str] = ..., timeout_s: _Optional[int] = ...) -> None: ...

class ContainerActionResponse(_message.Message):
    __slots__ = ("container",)
    CONTAINER_FIELD_NUMBER: _ClassVar[int]
    container: ContainerInfo
    def __init__(self, container: _Optional[_Union[ContainerInfo, _Mapping]] = ...) -> None: ...

class ContainerHostStatus(_message.Message):
    __slots__ = ("containers", "observed_at", "control_enabled", "trigger", "sequence")
    CONTAINERS_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    CONTROL_ENABLED_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    containers: _containers.RepeatedCompositeFieldContainer[ContainerInfo]
    observed_at: _timestamp_pb2.Timestamp
    control_enabled: bool
    trigger: StatusTrigger
    sequence: int
    def __init__(self, containers: _Optional[_Iterable[_Union[ContainerInfo, _Mapping]]] = ..., observed_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., control_enabled: bool = ..., trigger: _Optional[_Union[StatusTrigger, str]] = ..., sequence: _Optional[int] = ...) -> None: ...
