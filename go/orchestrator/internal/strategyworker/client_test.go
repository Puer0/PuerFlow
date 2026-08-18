package strategyworker

import (
	"testing"

	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
)

func TestKindFromMode(t *testing.T) {
	if KindFromMode("simple") != strategypb.StrategyKind_STRATEGY_KIND_SAMPLE {
		t.Fatalf("simple should map to sample, got %v", KindFromMode("simple"))
	}
	if got := KindFromMode("dag"); got != strategypb.StrategyKind_STRATEGY_KIND_DAG {
		t.Fatalf("dag kind=%v", got)
	}
}

func TestHistoryToMessages(t *testing.T) {
	msgs := HistoryToMessages([]string{"user: hi", "assistant: hello", "plain"})
	if len(msgs) != 3 {
		t.Fatalf("len=%d", len(msgs))
	}
	if msgs[0].Role != "user" || msgs[0].Content != "hi" {
		t.Fatalf("user parse: %+v", msgs[0])
	}
	if msgs[1].Role != "assistant" || msgs[1].Content != "hello" {
		t.Fatalf("assistant parse: %+v", msgs[1])
	}
	if msgs[2].Role != "user" || msgs[2].Content != "plain" {
		t.Fatalf("plain parse: %+v", msgs[2])
	}
}

func TestBuildRunRequest(t *testing.T) {
	req, err := BuildRunRequest(Request{
		WorkflowID: "wf-1",
		Query:      "hello",
		Mode:       "sample",
		SessionID:  "s1",
		History:    []string{"user: prior"},
		Context:    map[string]interface{}{"role": "generalist"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if req.GetWorkflowId() != "wf-1" || req.GetQuery() != "hello" {
		t.Fatalf("request: %+v", req)
	}
	if len(req.GetSession().GetHistory()) != 1 {
		t.Fatalf("history missing")
	}
}
