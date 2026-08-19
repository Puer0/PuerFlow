package strategyworker

import (
	"testing"

	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestEligibleForFailover(t *testing.T) {
	cases := []struct {
		name string
		mode string
		code strategypb.StrategyErrorCode
		err  error
		want bool
	}{
		{"dag strategy failed", "dag", strategypb.StrategyErrorCode_STRATEGY_ERROR_STRATEGY_FAILED, nil, true},
		{"research timeout", "research", strategypb.StrategyErrorCode_STRATEGY_ERROR_TIMEOUT, nil, true},
		{"swarm unavailable", "swarm", strategypb.StrategyErrorCode_STRATEGY_ERROR_UNAVAILABLE, nil, true},
		{"sample does not loop", "sample", strategypb.StrategyErrorCode_STRATEGY_ERROR_STRATEGY_FAILED, nil, false},
		{"simple does not loop", "simple", strategypb.StrategyErrorCode_STRATEGY_ERROR_TIMEOUT, nil, false},
		{"budget is hard stop", "dag", strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED, nil, false},
		{"cancel is not failover", "swarm", strategypb.StrategyErrorCode_STRATEGY_ERROR_CANCELLED, nil, false},
		{"rpc cancel", "dag", strategypb.StrategyErrorCode_STRATEGY_ERROR_UNSPECIFIED, status.Error(codes.Canceled, "cancelled"), false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := EligibleForFailover(tc.mode, tc.code, tc.err)
			if got != tc.want {
				t.Fatalf("got %v want %v", got, tc.want)
			}
		})
	}
}

func TestDecideFailover(t *testing.T) {
	hint := &strategypb.FailoverHint{
		ShouldFailover:    true,
		SuggestedStrategy: strategypb.StrategyKind_STRATEGY_KIND_SAMPLE,
		Reason:            "fallback to sample",
	}
	got := DecideFailover("dag", hint)
	if !got.Should || got.Mode != "sample" {
		t.Fatalf("unexpected decision: %+v", got)
	}
	if DecideFailover("sample", hint).Should {
		t.Fatal("sample should not failover onto itself")
	}
	if DecideFailover("research", nil).Should {
		t.Fatal("nil hint must not failover")
	}
}
