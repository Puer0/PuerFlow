package activities

import (
	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/validation"
)

// LinearizeCyclicPlan turns a cyclic dependency graph into a sequential chain
// so routing still has a path instead of failing before execution starts.
func LinearizeCyclicPlan(plan DecompositionResult) DecompositionResult {
	if len(plan.Subtasks) < 2 {
		return plan
	}
	infos := make([]validation.SubtaskInfo, len(plan.Subtasks))
	for i, st := range plan.Subtasks {
		infos[i] = validation.SubtaskInfo{ID: st.ID, Dependencies: st.Dependencies}
	}
	if !validation.DetectCyclicDependencies(infos).HasCycle {
		return plan
	}
	for i := range plan.Subtasks {
		if i == 0 {
			plan.Subtasks[i].Dependencies = []string{}
			continue
		}
		plan.Subtasks[i].Dependencies = []string{plan.Subtasks[i-1].ID}
	}
	plan.ExecutionStrategy = "sequential"
	if plan.Mode == "" {
		plan.Mode = "standard"
	}
	return plan
}
