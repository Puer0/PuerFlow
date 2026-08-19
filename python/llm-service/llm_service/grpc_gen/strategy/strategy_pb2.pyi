import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from common import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StrategyKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STRATEGY_KIND_UNSPECIFIED: _ClassVar[StrategyKind]
    STRATEGY_KIND_SAMPLE: _ClassVar[StrategyKind]
    STRATEGY_KIND_DAG: _ClassVar[StrategyKind]
    STRATEGY_KIND_RESEARCH: _ClassVar[StrategyKind]
    STRATEGY_KIND_SWARM: _ClassVar[StrategyKind]
    STRATEGY_KIND_SIMPLE: _ClassVar[StrategyKind]

class StrategyErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STRATEGY_ERROR_UNSPECIFIED: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_OK: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_INVALID_ARGUMENT: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_NOT_FOUND: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_CANCELLED: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_TIMEOUT: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_BUDGET_EXCEEDED: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_APPROVAL_REQUIRED: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_STRATEGY_FAILED: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_SANDBOX_FAILED: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_UNAVAILABLE: _ClassVar[StrategyErrorCode]
    STRATEGY_ERROR_FAILOVER: _ClassVar[StrategyErrorCode]

class StrategyTaskStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STRATEGY_TASK_STATUS_UNSPECIFIED: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_QUEUED: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_RUNNING: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_WAITING_APPROVAL: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_COMPLETED: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_FAILED: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_CANCELLED: _ClassVar[StrategyTaskStatus]
    STRATEGY_TASK_STATUS_TIMEOUT: _ClassVar[StrategyTaskStatus]
STRATEGY_KIND_UNSPECIFIED: StrategyKind
STRATEGY_KIND_SAMPLE: StrategyKind
STRATEGY_KIND_DAG: StrategyKind
STRATEGY_KIND_RESEARCH: StrategyKind
STRATEGY_KIND_SWARM: StrategyKind
STRATEGY_KIND_SIMPLE: StrategyKind
STRATEGY_ERROR_UNSPECIFIED: StrategyErrorCode
STRATEGY_ERROR_OK: StrategyErrorCode
STRATEGY_ERROR_INVALID_ARGUMENT: StrategyErrorCode
STRATEGY_ERROR_NOT_FOUND: StrategyErrorCode
STRATEGY_ERROR_CANCELLED: StrategyErrorCode
STRATEGY_ERROR_TIMEOUT: StrategyErrorCode
STRATEGY_ERROR_BUDGET_EXCEEDED: StrategyErrorCode
STRATEGY_ERROR_APPROVAL_REQUIRED: StrategyErrorCode
STRATEGY_ERROR_STRATEGY_FAILED: StrategyErrorCode
STRATEGY_ERROR_SANDBOX_FAILED: StrategyErrorCode
STRATEGY_ERROR_UNAVAILABLE: StrategyErrorCode
STRATEGY_ERROR_FAILOVER: StrategyErrorCode
STRATEGY_TASK_STATUS_UNSPECIFIED: StrategyTaskStatus
STRATEGY_TASK_STATUS_QUEUED: StrategyTaskStatus
STRATEGY_TASK_STATUS_RUNNING: StrategyTaskStatus
STRATEGY_TASK_STATUS_WAITING_APPROVAL: StrategyTaskStatus
STRATEGY_TASK_STATUS_COMPLETED: StrategyTaskStatus
STRATEGY_TASK_STATUS_FAILED: StrategyTaskStatus
STRATEGY_TASK_STATUS_CANCELLED: StrategyTaskStatus
STRATEGY_TASK_STATUS_TIMEOUT: StrategyTaskStatus

class AuthContext(_message.Message):
    __slots__ = ("user_id", "tenant_id", "api_key_id", "roles", "claims")
    class ClaimsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    API_KEY_ID_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    CLAIMS_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    tenant_id: str
    api_key_id: str
    roles: _containers.RepeatedScalarFieldContainer[str]
    claims: _containers.ScalarMap[str, str]
    def __init__(self, user_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., api_key_id: _Optional[str] = ..., roles: _Optional[_Iterable[str]] = ..., claims: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Budget(_message.Message):
    __slots__ = ("token_budget", "tokens_used", "prompt_tokens", "completion_tokens", "cost_usd_budget", "cost_usd_used", "warning_threshold", "near_limit", "exceeded", "model", "tier")
    TOKEN_BUDGET_FIELD_NUMBER: _ClassVar[int]
    TOKENS_USED_FIELD_NUMBER: _ClassVar[int]
    PROMPT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    COMPLETION_TOKENS_FIELD_NUMBER: _ClassVar[int]
    COST_USD_BUDGET_FIELD_NUMBER: _ClassVar[int]
    COST_USD_USED_FIELD_NUMBER: _ClassVar[int]
    WARNING_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    NEAR_LIMIT_FIELD_NUMBER: _ClassVar[int]
    EXCEEDED_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    token_budget: int
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd_budget: float
    cost_usd_used: float
    warning_threshold: float
    near_limit: bool
    exceeded: bool
    model: str
    tier: _common_pb2.ModelTier
    def __init__(self, token_budget: _Optional[int] = ..., tokens_used: _Optional[int] = ..., prompt_tokens: _Optional[int] = ..., completion_tokens: _Optional[int] = ..., cost_usd_budget: _Optional[float] = ..., cost_usd_used: _Optional[float] = ..., warning_threshold: _Optional[float] = ..., near_limit: _Optional[bool] = ..., exceeded: _Optional[bool] = ..., model: _Optional[str] = ..., tier: _Optional[_Union[_common_pb2.ModelTier, str]] = ...) -> None: ...

class MemoryHit(_message.Message):
    __slots__ = ("id", "content", "score", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    id: str
    content: str
    score: float
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, id: _Optional[str] = ..., content: _Optional[str] = ..., score: _Optional[float] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ConversationMessage(_message.Message):
    __slots__ = ("role", "content", "timestamp", "tokens_used")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TOKENS_USED_FIELD_NUMBER: _ClassVar[int]
    role: str
    content: str
    timestamp: _timestamp_pb2.Timestamp
    tokens_used: int
    def __init__(self, role: _Optional[str] = ..., content: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., tokens_used: _Optional[int] = ...) -> None: ...

class SessionPayload(_message.Message):
    __slots__ = ("session_id", "user_id", "history", "persistent_context", "files_created", "tools_used", "total_tokens_used", "total_cost_usd", "qdrant_hits")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    PERSISTENT_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    FILES_CREATED_FIELD_NUMBER: _ClassVar[int]
    TOOLS_USED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TOKENS_USED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COST_USD_FIELD_NUMBER: _ClassVar[int]
    QDRANT_HITS_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    user_id: str
    history: _containers.RepeatedCompositeFieldContainer[ConversationMessage]
    persistent_context: _struct_pb2.Struct
    files_created: _containers.RepeatedScalarFieldContainer[str]
    tools_used: _containers.RepeatedScalarFieldContainer[str]
    total_tokens_used: int
    total_cost_usd: float
    qdrant_hits: _containers.RepeatedCompositeFieldContainer[MemoryHit]
    def __init__(self, session_id: _Optional[str] = ..., user_id: _Optional[str] = ..., history: _Optional[_Iterable[_Union[ConversationMessage, _Mapping]]] = ..., persistent_context: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., files_created: _Optional[_Iterable[str]] = ..., tools_used: _Optional[_Iterable[str]] = ..., total_tokens_used: _Optional[int] = ..., total_cost_usd: _Optional[float] = ..., qdrant_hits: _Optional[_Iterable[_Union[MemoryHit, _Mapping]]] = ...) -> None: ...

class FailoverHint(_message.Message):
    __slots__ = ("should_failover", "suggested_strategy", "reason", "retryable")
    SHOULD_FAILOVER_FIELD_NUMBER: _ClassVar[int]
    SUGGESTED_STRATEGY_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    should_failover: bool
    suggested_strategy: StrategyKind
    reason: str
    retryable: bool
    def __init__(self, should_failover: _Optional[bool] = ..., suggested_strategy: _Optional[_Union[StrategyKind, str]] = ..., reason: _Optional[str] = ..., retryable: _Optional[bool] = ...) -> None: ...

class RunStrategyRequest(_message.Message):
    __slots__ = ("metadata", "workflow_id", "query", "strategy", "context", "session", "budget", "model_tier", "specific_model", "available_tools", "require_approval", "auth", "parent_workflow_id")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    BUDGET_FIELD_NUMBER: _ClassVar[int]
    MODEL_TIER_FIELD_NUMBER: _ClassVar[int]
    SPECIFIC_MODEL_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_TOOLS_FIELD_NUMBER: _ClassVar[int]
    REQUIRE_APPROVAL_FIELD_NUMBER: _ClassVar[int]
    AUTH_FIELD_NUMBER: _ClassVar[int]
    PARENT_WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    metadata: _common_pb2.TaskMetadata
    workflow_id: str
    query: str
    strategy: StrategyKind
    context: _struct_pb2.Struct
    session: SessionPayload
    budget: Budget
    model_tier: _common_pb2.ModelTier
    specific_model: str
    available_tools: _containers.RepeatedScalarFieldContainer[str]
    require_approval: bool
    auth: AuthContext
    parent_workflow_id: str
    def __init__(self, metadata: _Optional[_Union[_common_pb2.TaskMetadata, _Mapping]] = ..., workflow_id: _Optional[str] = ..., query: _Optional[str] = ..., strategy: _Optional[_Union[StrategyKind, str]] = ..., context: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., session: _Optional[_Union[SessionPayload, _Mapping]] = ..., budget: _Optional[_Union[Budget, _Mapping]] = ..., model_tier: _Optional[_Union[_common_pb2.ModelTier, str]] = ..., specific_model: _Optional[str] = ..., available_tools: _Optional[_Iterable[str]] = ..., require_approval: _Optional[bool] = ..., auth: _Optional[_Union[AuthContext, _Mapping]] = ..., parent_workflow_id: _Optional[str] = ...) -> None: ...

class RunStrategyResponse(_message.Message):
    __slots__ = ("workflow_id", "task_id", "status", "error_code", "task_status", "result", "error_message", "budget", "usage", "model_used", "provider", "metadata", "failover", "approval_required", "approval_id")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    TASK_STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    BUDGET_FIELD_NUMBER: _ClassVar[int]
    USAGE_FIELD_NUMBER: _ClassVar[int]
    MODEL_USED_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    FAILOVER_FIELD_NUMBER: _ClassVar[int]
    APPROVAL_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    APPROVAL_ID_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    status: _common_pb2.StatusCode
    error_code: StrategyErrorCode
    task_status: StrategyTaskStatus
    result: str
    error_message: str
    budget: Budget
    usage: _common_pb2.TokenUsage
    model_used: str
    provider: str
    metadata: _struct_pb2.Struct
    failover: FailoverHint
    approval_required: bool
    approval_id: str
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., status: _Optional[_Union[_common_pb2.StatusCode, str]] = ..., error_code: _Optional[_Union[StrategyErrorCode, str]] = ..., task_status: _Optional[_Union[StrategyTaskStatus, str]] = ..., result: _Optional[str] = ..., error_message: _Optional[str] = ..., budget: _Optional[_Union[Budget, _Mapping]] = ..., usage: _Optional[_Union[_common_pb2.TokenUsage, _Mapping]] = ..., model_used: _Optional[str] = ..., provider: _Optional[str] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., failover: _Optional[_Union[FailoverHint, _Mapping]] = ..., approval_required: _Optional[bool] = ..., approval_id: _Optional[str] = ...) -> None: ...

class CancelRequest(_message.Message):
    __slots__ = ("workflow_id", "task_id", "reason")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    reason: str
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class CancelResponse(_message.Message):
    __slots__ = ("accepted", "task_status", "message")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    TASK_STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    task_status: StrategyTaskStatus
    message: str
    def __init__(self, accepted: _Optional[bool] = ..., task_status: _Optional[_Union[StrategyTaskStatus, str]] = ..., message: _Optional[str] = ...) -> None: ...

class GetStatusRequest(_message.Message):
    __slots__ = ("workflow_id", "task_id", "include_details")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_DETAILS_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    include_details: bool
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., include_details: _Optional[bool] = ...) -> None: ...

class GetStatusResponse(_message.Message):
    __slots__ = ("workflow_id", "task_id", "task_status", "progress", "result", "error_message", "error_code", "budget", "failover", "current_step", "details")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_STATUS_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    BUDGET_FIELD_NUMBER: _ClassVar[int]
    FAILOVER_FIELD_NUMBER: _ClassVar[int]
    CURRENT_STEP_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    task_status: StrategyTaskStatus
    progress: float
    result: str
    error_message: str
    error_code: StrategyErrorCode
    budget: Budget
    failover: FailoverHint
    current_step: str
    details: _struct_pb2.Struct
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., task_status: _Optional[_Union[StrategyTaskStatus, str]] = ..., progress: _Optional[float] = ..., result: _Optional[str] = ..., error_message: _Optional[str] = ..., error_code: _Optional[_Union[StrategyErrorCode, str]] = ..., budget: _Optional[_Union[Budget, _Mapping]] = ..., failover: _Optional[_Union[FailoverHint, _Mapping]] = ..., current_step: _Optional[str] = ..., details: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class ApproveDecisionRequest(_message.Message):
    __slots__ = ("workflow_id", "task_id", "approval_id", "approved", "comment", "reviewer", "auth")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    APPROVAL_ID_FIELD_NUMBER: _ClassVar[int]
    APPROVED_FIELD_NUMBER: _ClassVar[int]
    COMMENT_FIELD_NUMBER: _ClassVar[int]
    REVIEWER_FIELD_NUMBER: _ClassVar[int]
    AUTH_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    approval_id: str
    approved: bool
    comment: str
    reviewer: str
    auth: AuthContext
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., approval_id: _Optional[str] = ..., approved: _Optional[bool] = ..., comment: _Optional[str] = ..., reviewer: _Optional[str] = ..., auth: _Optional[_Union[AuthContext, _Mapping]] = ...) -> None: ...

class ApproveDecisionResponse(_message.Message):
    __slots__ = ("applied", "task_status", "message")
    APPLIED_FIELD_NUMBER: _ClassVar[int]
    TASK_STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    applied: bool
    task_status: StrategyTaskStatus
    message: str
    def __init__(self, applied: _Optional[bool] = ..., task_status: _Optional[_Union[StrategyTaskStatus, str]] = ..., message: _Optional[str] = ...) -> None: ...

class BudgetReportRequest(_message.Message):
    __slots__ = ("workflow_id", "task_id", "session_id")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    session_id: str
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., session_id: _Optional[str] = ...) -> None: ...

class BudgetReportResponse(_message.Message):
    __slots__ = ("task_budget", "session_budget", "hard_stop", "degrade", "message")
    TASK_BUDGET_FIELD_NUMBER: _ClassVar[int]
    SESSION_BUDGET_FIELD_NUMBER: _ClassVar[int]
    HARD_STOP_FIELD_NUMBER: _ClassVar[int]
    DEGRADE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    task_budget: Budget
    session_budget: Budget
    hard_stop: bool
    degrade: bool
    message: str
    def __init__(self, task_budget: _Optional[_Union[Budget, _Mapping]] = ..., session_budget: _Optional[_Union[Budget, _Mapping]] = ..., hard_stop: _Optional[bool] = ..., degrade: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class InjectSessionContextRequest(_message.Message):
    __slots__ = ("workflow_id", "task_id", "session")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    session: SessionPayload
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., session: _Optional[_Union[SessionPayload, _Mapping]] = ...) -> None: ...

class InjectSessionContextResponse(_message.Message):
    __slots__ = ("applied", "history_messages", "qdrant_hits")
    APPLIED_FIELD_NUMBER: _ClassVar[int]
    HISTORY_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    QDRANT_HITS_FIELD_NUMBER: _ClassVar[int]
    applied: bool
    history_messages: int
    qdrant_hits: int
    def __init__(self, applied: _Optional[bool] = ..., history_messages: _Optional[int] = ..., qdrant_hits: _Optional[int] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("healthy", "version", "message")
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    healthy: bool
    version: str
    message: str
    def __init__(self, healthy: _Optional[bool] = ..., version: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class ReadyRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ReadyResponse(_message.Message):
    __slots__ = ("ready", "missing_dependencies", "message")
    READY_FIELD_NUMBER: _ClassVar[int]
    MISSING_DEPENDENCIES_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ready: bool
    missing_dependencies: _containers.RepeatedScalarFieldContainer[str]
    message: str
    def __init__(self, ready: _Optional[bool] = ..., missing_dependencies: _Optional[_Iterable[str]] = ..., message: _Optional[str] = ...) -> None: ...

class GetFailoverHintRequest(_message.Message):
    __slots__ = ("workflow_id", "task_id", "last_error", "failed_strategy")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_ERROR_FIELD_NUMBER: _ClassVar[int]
    FAILED_STRATEGY_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    task_id: str
    last_error: StrategyErrorCode
    failed_strategy: StrategyKind
    def __init__(self, workflow_id: _Optional[str] = ..., task_id: _Optional[str] = ..., last_error: _Optional[_Union[StrategyErrorCode, str]] = ..., failed_strategy: _Optional[_Union[StrategyKind, str]] = ...) -> None: ...

class GetFailoverHintResponse(_message.Message):
    __slots__ = ("hint",)
    HINT_FIELD_NUMBER: _ClassVar[int]
    hint: FailoverHint
    def __init__(self, hint: _Optional[_Union[FailoverHint, _Mapping]] = ...) -> None: ...
