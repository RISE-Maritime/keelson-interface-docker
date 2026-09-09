from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FileKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FILE_KIND_UNSPECIFIED: _ClassVar[FileKind]
    FILE_KIND_COMPOSE: _ClassVar[FileKind]
    FILE_KIND_YAML: _ClassVar[FileKind]
    FILE_KIND_ENV: _ClassVar[FileKind]
    FILE_KIND_JSON: _ClassVar[FileKind]
    FILE_KIND_MARKDOWN: _ClassVar[FileKind]
    FILE_KIND_OTHER: _ClassVar[FileKind]
FILE_KIND_UNSPECIFIED: FileKind
FILE_KIND_COMPOSE: FileKind
FILE_KIND_YAML: FileKind
FILE_KIND_ENV: FileKind
FILE_KIND_JSON: FileKind
FILE_KIND_MARKDOWN: FileKind
FILE_KIND_OTHER: FileKind

class RepoStatus(_message.Message):
    __slots__ = ("branch", "head_sha", "remote_url", "ahead", "behind", "dirty_paths", "last_fetch_at", "detached")
    BRANCH_FIELD_NUMBER: _ClassVar[int]
    HEAD_SHA_FIELD_NUMBER: _ClassVar[int]
    REMOTE_URL_FIELD_NUMBER: _ClassVar[int]
    AHEAD_FIELD_NUMBER: _ClassVar[int]
    BEHIND_FIELD_NUMBER: _ClassVar[int]
    DIRTY_PATHS_FIELD_NUMBER: _ClassVar[int]
    LAST_FETCH_AT_FIELD_NUMBER: _ClassVar[int]
    DETACHED_FIELD_NUMBER: _ClassVar[int]
    branch: str
    head_sha: str
    remote_url: str
    ahead: int
    behind: int
    dirty_paths: _containers.RepeatedScalarFieldContainer[str]
    last_fetch_at: _timestamp_pb2.Timestamp
    detached: bool
    def __init__(self, branch: _Optional[str] = ..., head_sha: _Optional[str] = ..., remote_url: _Optional[str] = ..., ahead: _Optional[int] = ..., behind: _Optional[int] = ..., dirty_paths: _Optional[_Iterable[str]] = ..., last_fetch_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., detached: bool = ...) -> None: ...

class CommitInfo(_message.Message):
    __slots__ = ("sha", "message", "author_name", "author_email", "committed_at", "operator_id")
    SHA_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_NAME_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_EMAIL_FIELD_NUMBER: _ClassVar[int]
    COMMITTED_AT_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    sha: str
    message: str
    author_name: str
    author_email: str
    committed_at: _timestamp_pb2.Timestamp
    operator_id: str
    def __init__(self, sha: _Optional[str] = ..., message: _Optional[str] = ..., author_name: _Optional[str] = ..., author_email: _Optional[str] = ..., committed_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., operator_id: _Optional[str] = ...) -> None: ...

class EntityInfo(_message.Message):
    __slots__ = ("name", "relative_path", "file_count", "service_count", "has_readme", "dirty")
    NAME_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_PATH_FIELD_NUMBER: _ClassVar[int]
    FILE_COUNT_FIELD_NUMBER: _ClassVar[int]
    SERVICE_COUNT_FIELD_NUMBER: _ClassVar[int]
    HAS_README_FIELD_NUMBER: _ClassVar[int]
    DIRTY_FIELD_NUMBER: _ClassVar[int]
    name: str
    relative_path: str
    file_count: int
    service_count: int
    has_readme: bool
    dirty: bool
    def __init__(self, name: _Optional[str] = ..., relative_path: _Optional[str] = ..., file_count: _Optional[int] = ..., service_count: _Optional[int] = ..., has_readme: bool = ..., dirty: bool = ...) -> None: ...

class FileInfo(_message.Message):
    __slots__ = ("name", "relative_path", "size_bytes", "modified_at", "kind", "dirty", "writable", "deletable")
    NAME_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_PATH_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    MODIFIED_AT_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    DIRTY_FIELD_NUMBER: _ClassVar[int]
    WRITABLE_FIELD_NUMBER: _ClassVar[int]
    DELETABLE_FIELD_NUMBER: _ClassVar[int]
    name: str
    relative_path: str
    size_bytes: int
    modified_at: _timestamp_pb2.Timestamp
    kind: FileKind
    dirty: bool
    writable: bool
    deletable: bool
    def __init__(self, name: _Optional[str] = ..., relative_path: _Optional[str] = ..., size_bytes: _Optional[int] = ..., modified_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., kind: _Optional[_Union[FileKind, str]] = ..., dirty: bool = ..., writable: bool = ..., deletable: bool = ...) -> None: ...

class ListEntitiesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListEntitiesResponse(_message.Message):
    __slots__ = ("entities", "repo", "observed_at", "write_enabled", "delete_enabled", "git_enabled", "push_enabled")
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    REPO_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    WRITE_ENABLED_FIELD_NUMBER: _ClassVar[int]
    DELETE_ENABLED_FIELD_NUMBER: _ClassVar[int]
    GIT_ENABLED_FIELD_NUMBER: _ClassVar[int]
    PUSH_ENABLED_FIELD_NUMBER: _ClassVar[int]
    entities: _containers.RepeatedCompositeFieldContainer[EntityInfo]
    repo: RepoStatus
    observed_at: _timestamp_pb2.Timestamp
    write_enabled: bool
    delete_enabled: bool
    git_enabled: bool
    push_enabled: bool
    def __init__(self, entities: _Optional[_Iterable[_Union[EntityInfo, _Mapping]]] = ..., repo: _Optional[_Union[RepoStatus, _Mapping]] = ..., observed_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., write_enabled: bool = ..., delete_enabled: bool = ..., git_enabled: bool = ..., push_enabled: bool = ...) -> None: ...

class ListFilesRequest(_message.Message):
    __slots__ = ("entity",)
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    entity: str
    def __init__(self, entity: _Optional[str] = ...) -> None: ...

class ListFilesResponse(_message.Message):
    __slots__ = ("entity", "files", "observed_at")
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    entity: str
    files: _containers.RepeatedCompositeFieldContainer[FileInfo]
    observed_at: _timestamp_pb2.Timestamp
    def __init__(self, entity: _Optional[str] = ..., files: _Optional[_Iterable[_Union[FileInfo, _Mapping]]] = ..., observed_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ReadFileRequest(_message.Message):
    __slots__ = ("path",)
    PATH_FIELD_NUMBER: _ClassVar[int]
    path: str
    def __init__(self, path: _Optional[str] = ...) -> None: ...

class ReadFileResponse(_message.Message):
    __slots__ = ("path", "content", "sha256", "size_bytes", "modified_at", "writable", "truncated")
    PATH_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    MODIFIED_AT_FIELD_NUMBER: _ClassVar[int]
    WRITABLE_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    path: str
    content: bytes
    sha256: str
    size_bytes: int
    modified_at: _timestamp_pb2.Timestamp
    writable: bool
    truncated: bool
    def __init__(self, path: _Optional[str] = ..., content: _Optional[bytes] = ..., sha256: _Optional[str] = ..., size_bytes: _Optional[int] = ..., modified_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., writable: bool = ..., truncated: bool = ...) -> None: ...

class WriteFileRequest(_message.Message):
    __slots__ = ("path", "content", "base_sha256", "commit_message", "operator_id")
    PATH_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    BASE_SHA256_FIELD_NUMBER: _ClassVar[int]
    COMMIT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    path: str
    content: bytes
    base_sha256: str
    commit_message: str
    operator_id: str
    def __init__(self, path: _Optional[str] = ..., content: _Optional[bytes] = ..., base_sha256: _Optional[str] = ..., commit_message: _Optional[str] = ..., operator_id: _Optional[str] = ...) -> None: ...

class WriteFileResponse(_message.Message):
    __slots__ = ("path", "sha256", "commit", "pushed", "push_error", "repo")
    PATH_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    COMMIT_FIELD_NUMBER: _ClassVar[int]
    PUSHED_FIELD_NUMBER: _ClassVar[int]
    PUSH_ERROR_FIELD_NUMBER: _ClassVar[int]
    REPO_FIELD_NUMBER: _ClassVar[int]
    path: str
    sha256: str
    commit: CommitInfo
    pushed: bool
    push_error: str
    repo: RepoStatus
    def __init__(self, path: _Optional[str] = ..., sha256: _Optional[str] = ..., commit: _Optional[_Union[CommitInfo, _Mapping]] = ..., pushed: bool = ..., push_error: _Optional[str] = ..., repo: _Optional[_Union[RepoStatus, _Mapping]] = ...) -> None: ...

class DeleteFileRequest(_message.Message):
    __slots__ = ("path", "base_sha256", "commit_message", "operator_id")
    PATH_FIELD_NUMBER: _ClassVar[int]
    BASE_SHA256_FIELD_NUMBER: _ClassVar[int]
    COMMIT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_ID_FIELD_NUMBER: _ClassVar[int]
    path: str
    base_sha256: str
    commit_message: str
    operator_id: str
    def __init__(self, path: _Optional[str] = ..., base_sha256: _Optional[str] = ..., commit_message: _Optional[str] = ..., operator_id: _Optional[str] = ...) -> None: ...

class DeleteFileResponse(_message.Message):
    __slots__ = ("path", "commit", "pushed", "push_error", "repo")
    PATH_FIELD_NUMBER: _ClassVar[int]
    COMMIT_FIELD_NUMBER: _ClassVar[int]
    PUSHED_FIELD_NUMBER: _ClassVar[int]
    PUSH_ERROR_FIELD_NUMBER: _ClassVar[int]
    REPO_FIELD_NUMBER: _ClassVar[int]
    path: str
    commit: CommitInfo
    pushed: bool
    push_error: str
    repo: RepoStatus
    def __init__(self, path: _Optional[str] = ..., commit: _Optional[_Union[CommitInfo, _Mapping]] = ..., pushed: bool = ..., push_error: _Optional[str] = ..., repo: _Optional[_Union[RepoStatus, _Mapping]] = ...) -> None: ...

class RepoStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RepoStatusResponse(_message.Message):
    __slots__ = ("repo", "write_enabled", "delete_enabled", "git_enabled", "push_enabled")
    REPO_FIELD_NUMBER: _ClassVar[int]
    WRITE_ENABLED_FIELD_NUMBER: _ClassVar[int]
    DELETE_ENABLED_FIELD_NUMBER: _ClassVar[int]
    GIT_ENABLED_FIELD_NUMBER: _ClassVar[int]
    PUSH_ENABLED_FIELD_NUMBER: _ClassVar[int]
    repo: RepoStatus
    write_enabled: bool
    delete_enabled: bool
    git_enabled: bool
    push_enabled: bool
    def __init__(self, repo: _Optional[_Union[RepoStatus, _Mapping]] = ..., write_enabled: bool = ..., delete_enabled: bool = ..., git_enabled: bool = ..., push_enabled: bool = ...) -> None: ...

class SyncRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SyncResponse(_message.Message):
    __slots__ = ("repo", "rebased", "conflict")
    REPO_FIELD_NUMBER: _ClassVar[int]
    REBASED_FIELD_NUMBER: _ClassVar[int]
    CONFLICT_FIELD_NUMBER: _ClassVar[int]
    repo: RepoStatus
    rebased: bool
    conflict: str
    def __init__(self, repo: _Optional[_Union[RepoStatus, _Mapping]] = ..., rebased: bool = ..., conflict: _Optional[str] = ...) -> None: ...
