package activities

import "testing"

func TestHeuristicDecompose_ConjunctionsBecomeDAGShaped(t *testing.T) {
	got := HeuristicDecompose("先查汇率然后换算成人民币而且写结论")
	if len(got.Subtasks) != 3 {
		t.Fatalf("subtasks=%d want 3: %#v", len(got.Subtasks), got.Subtasks)
	}
	if got.Subtasks[1].Dependencies[0] != "1" {
		t.Fatalf("second step should depend on first, got %v", got.Subtasks[1].Dependencies)
	}
	if got.ComplexityScore < 0.3 {
		t.Fatalf("complexity=%v, expected enough to avoid simple-only fallback", got.ComplexityScore)
	}
	if got.Mode == "simple" && len(got.Subtasks) > 1 {
		t.Fatalf("multi-step heuristic plan should not stay in simple mode")
	}
}

func TestHeuristicDecompose_SingleStepStaysLight(t *testing.T) {
	got := HeuristicDecompose("What is the capital of France?")
	if len(got.Subtasks) != 1 {
		t.Fatalf("subtasks=%d want 1", len(got.Subtasks))
	}
	if got.ComplexityScore >= 0.3 {
		t.Fatalf("simple question complexity=%v", got.ComplexityScore)
	}
}
