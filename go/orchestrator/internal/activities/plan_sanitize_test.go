package activities

import "testing"

func TestLinearizeCyclicPlan_BreaksCycle(t *testing.T) {
	plan := DecompositionResult{
		Subtasks: []Subtask{
			{ID: "a", Dependencies: []string{"c"}},
			{ID: "b", Dependencies: []string{"a"}},
			{ID: "c", Dependencies: []string{"b"}},
		},
	}
	got := LinearizeCyclicPlan(plan)
	if len(got.Subtasks[0].Dependencies) != 0 {
		t.Fatalf("first step should have no deps, got %v", got.Subtasks[0].Dependencies)
	}
	if got.Subtasks[2].Dependencies[0] != "b" {
		t.Fatalf("expected sequential chain, got %#v", got.Subtasks)
	}
}

func TestLinearizeCyclicPlan_KeepsAcyclic(t *testing.T) {
	plan := DecompositionResult{
		Subtasks: []Subtask{
			{ID: "a"},
			{ID: "b", Dependencies: []string{"a"}},
		},
	}
	got := LinearizeCyclicPlan(plan)
	if got.Subtasks[1].Dependencies[0] != "a" {
		t.Fatalf("acyclic deps should stay, got %#v", got.Subtasks[1])
	}
}
