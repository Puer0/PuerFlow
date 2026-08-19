package strategyworker

import "testing"

func TestKindFromMode(t *testing.T) {
	cases := map[string]string{
		"simple":     "STRATEGY_KIND_SAMPLE",
		"sample":     "STRATEGY_KIND_SAMPLE",
		"":           "STRATEGY_KIND_SAMPLE",
		"dag":        "STRATEGY_KIND_DAG",
		"complex":    "STRATEGY_KIND_DAG",
		"research":   "STRATEGY_KIND_RESEARCH",
		"swarm":      "STRATEGY_KIND_SWARM",
		"multi_agent": "STRATEGY_KIND_SWARM",
	}
	for mode, want := range cases {
		got := KindFromMode(mode).String()
		if got != want {
			t.Fatalf("mode %q: got %s want %s", mode, got, want)
		}
	}
}

func TestHistoryToMessages(t *testing.T) {
	msgs := HistoryToMessages([]string{"user: hi", "assistant: hello", "plain"})
	if len(msgs) != 3 {
		t.Fatalf("got %d messages", len(msgs))
	}
	if msgs[0].Role != "user" || msgs[1].Role != "assistant" || msgs[2].Role != "user" {
		t.Fatalf("unexpected roles: %+v", msgs)
	}
}
