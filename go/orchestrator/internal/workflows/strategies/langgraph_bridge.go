package strategies

import (
	"fmt"
	"strings"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/activities"
)

func maybeRunLangGraph(ctx workflow.Context, input TaskInput, mode, workflowID string) (TaskResult, bool, error) {
	version := workflow.GetVersion(ctx, "langgraph_strategy_v1", workflow.DefaultVersion, 1)
	if version < 1 {
		return TaskResult{}, false, nil
	}

	history := make([]string, 0, len(input.History))
	for _, msg := range input.History {
		if strings.TrimSpace(msg.Content) == "" {
			continue
		}
		role := msg.Role
		if role == "" {
			role = "user"
		}
		history = append(history, role+": "+msg.Content)
	}

	merged := make(map[string]interface{})
	for k, v := range input.SessionCtx {
		merged[k] = v
	}
	for k, v := range input.Context {
		merged[k] = v
	}

	lgCtx := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Minute,
		RetryPolicy: &temporal.RetryPolicy{
			MaximumAttempts:        2,
			NonRetryableErrorTypes: []string{"CanceledError"},
		},
	})

	var out activities.LangGraphTaskResult
	err := workflow.ExecuteActivity(lgCtx, activities.ExecuteLangGraphIfEnabled, activities.LangGraphTaskInput{
		ExecuteSimpleTaskInput: activities.ExecuteSimpleTaskInput{
			Query:            input.Query,
			UserID:           input.UserID,
			SessionID:        input.SessionID,
			Context:          merged,
			SessionCtx:       input.SessionCtx,
			History:          history,
			ParentWorkflowID: workflowID,
			Mode:             mode,
			RequireApproval:  input.RequireApproval,
			TenantID:         input.TenantID,
		},
		Mode:            mode,
		RequireApproval: input.RequireApproval,
		TenantID:        input.TenantID,
	}).Get(ctx, &out)
	if err != nil {
		return TaskResult{Success: false, ErrorMessage: err.Error()}, true, err
	}
	if !out.Used {
		return TaskResult{}, false, nil
	}
	result := TaskResult{
		Result:       out.Response,
		Success:      out.Success,
		TokensUsed:   out.TokensUsed,
		ErrorMessage: out.Error,
		Metadata: map[string]interface{}{
			"langgraph": true,
			"mode":      mode,
		},
	}
	if !out.Success {
		msg := out.Error
		if msg == "" {
			msg = fmt.Sprintf("langgraph %s failed", mode)
		}
		result.ErrorMessage = msg
		return result, true, fmt.Errorf("%s", msg)
	}
	return result, true, nil
}
