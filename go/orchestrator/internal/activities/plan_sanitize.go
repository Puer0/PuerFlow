package activities

import (
	"strings"

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

// CorrectPlanRouting applies deterministic upgrades/downgrades after planning.
// Explicit force flags win; a lone research recommendation without research signals
// drops to DAG/Sample; a simple label with multiple steps or deps rises to DAG.
func CorrectPlanRouting(plan DecompositionResult, forceResearch, forceSwarm bool) DecompositionResult {
	if forceResearch || forceSwarm {
		return plan
	}

	joined := ""
	for _, st := range plan.Subtasks {
		joined += " " + st.Description
	}
	hasResearchSignal := researchHints.MatchString(joined)

	cog := strings.ToLower(strings.TrimSpace(plan.CognitiveStrategy))
	if (cog == "research" || strings.EqualFold(plan.Mode, "research")) && !hasResearchSignal {
		if len(plan.Subtasks) <= 1 && plan.ComplexityScore < 0.3 {
			plan.CognitiveStrategy = ""
			plan.Mode = "simple"
		} else {
			plan.CognitiveStrategy = ""
			plan.Mode = "standard"
			if plan.ComplexityScore < 0.3 {
				plan.ComplexityScore = 0.35
			}
		}
	}

	hasDeps := false
	for _, st := range plan.Subtasks {
		if len(st.Dependencies) > 0 {
			hasDeps = true
			break
		}
	}
	simpleLabel := cog == "direct" || cog == "simple" || cog == "sample" || strings.EqualFold(plan.Mode, "simple")
	if simpleLabel && (len(plan.Subtasks) > 1 || hasDeps) {
		plan.CognitiveStrategy = ""
		plan.Mode = "standard"
		if plan.ComplexityScore < 0.3 {
			plan.ComplexityScore = 0.35
		}
	}
	return plan
}

// AttachPreplannedContext copies the orchestrator plan into the Worker request context.
func AttachPreplannedContext(ctx map[string]interface{}, plan *DecompositionResult) {
	if ctx == nil || plan == nil {
		return
	}
	steps := make([]interface{}, 0, len(plan.Subtasks))
	for _, st := range plan.Subtasks {
		tools := make([]interface{}, 0, len(st.SuggestedTools))
		for _, name := range st.SuggestedTools {
			tools = append(tools, name)
		}
		deps := make([]interface{}, 0, len(st.Dependencies))
		for _, dep := range st.Dependencies {
			deps = append(deps, dep)
		}
		item := map[string]interface{}{
			"id":              st.ID,
			"description":     st.Description,
			"dependencies":    deps,
			"suggested_tools": tools,
		}
		if st.ToolParameters != nil {
			item["tool_parameters"] = st.ToolParameters
		}
		steps = append(steps, item)
	}
	ctx["preplanned_subtasks"] = steps
	ctx["preplanned_complexity"] = plan.ComplexityScore
}

