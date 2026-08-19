package activities

import (
	"context"
	"testing"

	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/strategyworker"
	"go.temporal.io/sdk/testsuite"
)

func TestExecuteLangGraphIfEnabledFailsoverToSample(t *testing.T) {
	t.Setenv("LANGGRAPH_WORKER_ENABLED", "1")
	t.Setenv("LANGGRAPH_WORKER_ADDR", "localhost:1")

	origRun := langGraphRun
	origHint := langGraphHint
	t.Cleanup(func() {
		langGraphRun = origRun
		langGraphHint = origHint
	})

	var modes []string
	langGraphRun = func(ctx context.Context, in strategyworker.Request) (*strategypb.RunStrategyResponse, error) {
		modes = append(modes, in.Mode)
		if in.Mode == "dag" {
			return &strategypb.RunStrategyResponse{
				ErrorCode:    strategypb.StrategyErrorCode_STRATEGY_ERROR_STRATEGY_FAILED,
				ErrorMessage: "graph exploded",
				Failover: &strategypb.FailoverHint{
					ShouldFailover:    true,
					SuggestedStrategy: strategypb.StrategyKind_STRATEGY_KIND_SAMPLE,
					Reason:            "fallback to sample",
					Retryable:         true,
				},
			}, nil
		}
		return &strategypb.RunStrategyResponse{
			Result:    "sample-ok",
			ErrorCode: strategypb.StrategyErrorCode_STRATEGY_ERROR_OK,
		}, nil
	}
	langGraphHint = func(ctx context.Context, workflowID, taskID string, lastError strategypb.StrategyErrorCode, failedMode string) (*strategypb.GetFailoverHintResponse, error) {
		t.Fatal("hint already on RunStrategyResponse; extra RPC should be skipped")
		return nil, nil
	}

	suite := &testsuite.WorkflowTestSuite{}
	env := suite.NewTestActivityEnvironment()
	env.RegisterActivity(ExecuteLangGraphIfEnabled)
	encoded, err := env.ExecuteActivity(ExecuteLangGraphIfEnabled, LangGraphTaskInput{
		ExecuteSimpleTaskInput: ExecuteSimpleTaskInput{
			Query:            "q",
			ParentWorkflowID: "wf-1",
		},
		Mode: "dag",
	})
	if err != nil {
		t.Fatalf("activity failed: %v", err)
	}
	var out LangGraphTaskResult
	if err := encoded.Get(&out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !out.Used || !out.Success || !out.Failover {
		t.Fatalf("unexpected result: %+v", out)
	}
	if out.Response != "sample-ok" || out.OriginalMode != "dag" || out.FailoverMode != "sample" {
		t.Fatalf("unexpected failover fields: %+v", out)
	}
	if len(modes) != 2 || modes[0] != "dag" || modes[1] != "sample" {
		t.Fatalf("unexpected run order: %v", modes)
	}
}

func TestExecuteLangGraphIfEnabledDoesNotFailoverBudget(t *testing.T) {
	t.Setenv("LANGGRAPH_WORKER_ENABLED", "1")
	t.Setenv("LANGGRAPH_WORKER_ADDR", "localhost:1")

	origRun := langGraphRun
	origHint := langGraphHint
	t.Cleanup(func() {
		langGraphRun = origRun
		langGraphHint = origHint
	})

	runs := 0
	langGraphRun = func(ctx context.Context, in strategyworker.Request) (*strategypb.RunStrategyResponse, error) {
		runs++
		return &strategypb.RunStrategyResponse{
			ErrorCode:    strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED,
			ErrorMessage: "budget exceeded",
		}, nil
	}
	langGraphHint = func(ctx context.Context, workflowID, taskID string, lastError strategypb.StrategyErrorCode, failedMode string) (*strategypb.GetFailoverHintResponse, error) {
		t.Fatal("budget must not call GetFailoverHint")
		return nil, nil
	}

	suite := &testsuite.WorkflowTestSuite{}
	env := suite.NewTestActivityEnvironment()
	env.RegisterActivity(ExecuteLangGraphIfEnabled)
	_, err := env.ExecuteActivity(ExecuteLangGraphIfEnabled, LangGraphTaskInput{
		ExecuteSimpleTaskInput: ExecuteSimpleTaskInput{Query: "q", ParentWorkflowID: "wf-budget"},
		Mode:                   "research",
	})
	if err == nil {
		t.Fatal("expected budget error")
	}
	if runs != 1 {
		t.Fatalf("expected one run, got %d", runs)
	}
}
