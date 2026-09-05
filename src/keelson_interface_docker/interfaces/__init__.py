"""Generated ContainerControl bindings.

UPSTREAMING SWAP POINT. Every other module in this package imports the message
classes from HERE, never from ``ContainerControl_pb2`` directly, so moving to
keelson's copy once the interface lands upstream is this file and nothing else::

    from .ContainerControl_pb2 import (...)                      # before
    from keelson.interfaces.ContainerControl_pb2 import (...)    # after

The two copies cannot coexist: both register
``keelson.interfaces.container_control.*`` in protobuf's default descriptor
pool, and the second registration raises ``TypeError: Couldn't build proto file
into descriptor pool: duplicate file name``. That is by design -- it makes a
half-finished migration fail loudly at import rather than quietly serving two
descriptors.
"""

from .ContainerControl_pb2 import (
    ContainerActionResponse,
    ContainerHostStats,
    ContainerHostStatus,
    ContainerInfo,
    ContainerResourceUsage,
    ContainerState,
    GetLogsRequest,
    GetLogsResponse,
    HealthStatus,
    ListContainersRequest,
    ListContainersResponse,
    LogLine,
    LogStream,
    LogStreamSelector,
    RemoveContainerRequest,
    RemoveContainerResponse,
    RestartContainerRequest,
    RestartPolicy,
    StartContainerRequest,
    StatusTrigger,
    StopContainerRequest,
)

#: The ``{interface}/{version}`` this repo serves, as it appears in the keelson
#: RPC key space and in ``interfaces/interfaces.yaml``.
INTERFACE = "container_control"
VERSION = "v1"

__all__ = [
    "INTERFACE",
    "VERSION",
    "ContainerActionResponse",
    "ContainerHostStats",
    "ContainerHostStatus",
    "ContainerInfo",
    "ContainerResourceUsage",
    "ContainerState",
    "GetLogsRequest",
    "GetLogsResponse",
    "HealthStatus",
    "ListContainersRequest",
    "ListContainersResponse",
    "LogLine",
    "LogStream",
    "LogStreamSelector",
    "RemoveContainerRequest",
    "RemoveContainerResponse",
    "RestartContainerRequest",
    "RestartPolicy",
    "StartContainerRequest",
    "StatusTrigger",
    "StopContainerRequest",
]
