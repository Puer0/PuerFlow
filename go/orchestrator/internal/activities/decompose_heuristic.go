package activities

import (
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"
)

var heuristicSplitters = regexp.MustCompile(
	`(?i)\s*(?:;|；|而且|并且|然后|and then|then|, and )\s*`,
)

var researchHints = regexp.MustCompile(
	`(?i)调研|研究|对比|比较|引用|最新|时效|cite|compare|versus|\bvs\b|research`,
)

// HeuristicDecompose splits a query on conjunctions when the LLM planner is unavailable.
// Multi-step results keep enough complexity to route into DAG instead of pretending the task is simple.
func HeuristicDecompose(query string) DecompositionResult {
	query = strings.TrimSpace(query)
	parts := splitHeuristicParts(query)
	if len(parts) == 0 {
		parts = []string{query}
	}

	subtasks := make([]Subtask, 0, len(parts))
	for i, part := range parts {
		id := fmt.Sprintf("%d", i+1)
		deps := []string{}
		if i > 0 {
			deps = []string{fmt.Sprintf("%d", i)}
		}
		subtasks = append(subtasks, Subtask{
			ID:              id,
			Description:     part,
			Dependencies:    deps,
			TaskType:        "generic",
			EstimatedTokens: 2000,
		})
	}

	score := heuristicComplexity(query, len(subtasks))
	mode := "simple"
	strategy := "sequential"
	if len(subtasks) > 1 || score >= 0.3 {
		mode = "standard"
	}
	if len(subtasks) > 1 {
		strategy = "sequential"
	}

	return DecompositionResult{
		Mode:                 mode,
		ComplexityScore:      score,
		ExecutionStrategy:    strategy,
		CognitiveStrategy:    "",
		Subtasks:             subtasks,
		TotalEstimatedTokens: 2000 * len(subtasks),
	}
}

func splitHeuristicParts(query string) []string {
	if query == "" {
		return nil
	}
	raw := heuristicSplitters.Split(query, -1)
	out := make([]string, 0, len(raw))
	for _, part := range raw {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	if len(out) > 6 {
		return out[:6]
	}
	return out
}

func heuristicComplexity(query string, steps int) float64 {
	score := 0.15
	if steps >= 2 {
		score = 0.35
	}
	if steps >= 4 {
		score = 0.5
	}
	if utf8.RuneCountInString(query) > 80 {
		score += 0.1
	}
	if researchHints.MatchString(query) {
		score += 0.15
	}
	if score > 0.85 {
		return 0.85
	}
	return score
}
