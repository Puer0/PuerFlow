package activities

import (
	"strings"
	"testing"
)

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

func TestCorrectPlanRouting_DowngradesBareResearch(t *testing.T) {
	plan := DecompositionResult{
		Mode:              "research",
		CognitiveStrategy: "research",
		ComplexityScore:   0.2,
		Subtasks:          []Subtask{{ID: "1", Description: "What is 2+2?"}},
	}
	got := CorrectPlanRouting(plan, false, false)
	if got.CognitiveStrategy == "research" || strings.EqualFold(got.Mode, "research") {
		t.Fatalf("expected research downgrade, got mode=%s cog=%s", got.Mode, got.CognitiveStrategy)
	}
}

func TestCorrectPlanRouting_UpgradesSimpleMultiStep(t *testing.T) {
	plan := DecompositionResult{
		Mode:              "simple",
		CognitiveStrategy: "simple",
		ComplexityScore:   0.1,
		Subtasks: []Subtask{
			{ID: "1", Description: "step one"},
			{ID: "2", Description: "step two", Dependencies: []string{"1"}},
		},
	}
	got := CorrectPlanRouting(plan, false, false)
	if got.Mode != "standard" || got.ComplexityScore < 0.3 {
		t.Fatalf("expected DAG-shaped upgrade, got mode=%s score=%v", got.Mode, got.ComplexityScore)
	}
}
