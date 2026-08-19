package strategyworker

import (
	"strings"

	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type FailoverDecision struct {
	Should bool
	Mode   string
	Reason string
}

func ModeFromKind(kind strategypb.StrategyKind) string {
	switch kind {
	case strategypb.StrategyKind_STRATEGY_KIND_DAG:
		return "dag"
	case strategypb.StrategyKind_STRATEGY_KIND_RESEARCH:
		return "research"
	case strategypb.StrategyKind_STRATEGY_KIND_SWARM:
		return "swarm"
	case strategypb.StrategyKind_STRATEGY_KIND_SIMPLE, strategypb.StrategyKind_STRATEGY_KIND_SAMPLE:
		return "sample"
	default:
		return "sample"
	}
}

func IsLightMode(mode string) bool {
	switch KindFromMode(mode) {
	case strategypb.StrategyKind_STRATEGY_KIND_SAMPLE, strategypb.StrategyKind_STRATEGY_KIND_SIMPLE:
		return true
	default:
		return strings.TrimSpace(mode) == ""
	}
}

func ErrorCodeFromRPC(err error) strategypb.StrategyErrorCode {
	if err == nil {
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_OK
	}
	st, ok := status.FromError(err)
	if !ok {
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_UNAVAILABLE
	}
	switch st.Code() {
	case codes.Canceled:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_CANCELLED
	case codes.DeadlineExceeded:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_TIMEOUT
	case codes.ResourceExhausted:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED
	case codes.InvalidArgument:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_INVALID_ARGUMENT
	case codes.NotFound:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_NOT_FOUND
	case codes.Unavailable:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_UNAVAILABLE
	default:
		return strategypb.StrategyErrorCode_STRATEGY_ERROR_STRATEGY_FAILED
	}
}

func EligibleForFailover(mode string, code strategypb.StrategyErrorCode, err error) bool {
	if IsLightMode(mode) {
		return false
	}
	switch code {
	case strategypb.StrategyErrorCode_STRATEGY_ERROR_CANCELLED,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_INVALID_ARGUMENT,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_APPROVAL_REQUIRED,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_OK:
		return false
	case strategypb.StrategyErrorCode_STRATEGY_ERROR_STRATEGY_FAILED,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_TIMEOUT,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_UNAVAILABLE,
		strategypb.StrategyErrorCode_STRATEGY_ERROR_FAILOVER:
		return true
	}
	if err == nil {
		return false
	}
	if st, ok := status.FromError(err); ok {
		switch st.Code() {
		case codes.Canceled, codes.ResourceExhausted:
			return false
		}
	}
	return true
}

func DecideFailover(failedMode string, hint *strategypb.FailoverHint) FailoverDecision {
	if hint == nil || !hint.GetShouldFailover() {
		return FailoverDecision{}
	}
	suggested := ModeFromKind(hint.GetSuggestedStrategy())
	if suggested == "" {
		suggested = "sample"
	}
	if KindFromMode(failedMode) == KindFromMode(suggested) {
		return FailoverDecision{}
	}
	reason := strings.TrimSpace(hint.GetReason())
	if reason == "" {
		reason = "fallback to sample"
	}
	return FailoverDecision{Should: true, Mode: suggested, Reason: reason}
}
