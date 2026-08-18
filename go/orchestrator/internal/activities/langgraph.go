package activities

import (
	"context"
	"os"
	"time"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/strategyworker"
	"go.temporal.io/sdk/activity"
	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func ExecuteLangGraphStrategy(ctx context.Context, input ExecuteSimpleTaskInput) (ExecuteSimpleTaskResult, error) {
	logger := activity.GetLogger(ctx)
	logger.Info("ExecuteLangGraphStrategy started",
		"query", input.Query,
		"session_id", input.SessionID,
		"workflow_id", input.ParentWorkflowID,
	)

	tokenBudget := int32(0)
	if input.Context != nil {
		if v, ok := input.Context["token_budget"].(float64); ok {
			tokenBudget = int32(v)
		}
	}

	callCtx, cancel := context.WithTimeout(ctx, 10*time.Minute)
	defer cancel()

	resp, err := strategyworker.Run(callCtx, strategyworker.Request{
		WorkflowID:  input.ParentWorkflowID,
		TaskID:      input.ParentWorkflowID,
		Query:       input.Query,
		Mode:        "simple",
		UserID:      input.UserID,
		SessionID:   input.SessionID,
		Context:     input.Context,
		History:     input.History,
		TokenBudget: tokenBudget,
	})
	if err != nil {
		if st, ok := status.FromError(err); ok && st.Code() == codes.Canceled {
			return ExecuteSimpleTaskResult{Success: false, Error: "cancelled"}, err
		}
		zap.L().Error("LangGraph worker call failed", zap.Error(err))
		return ExecuteSimpleTaskResult{Success: false, Error: err.Error()}, err
	}

	ok := resp.GetErrorCode() == 1 || resp.GetResult() != "" // STRATEGY_ERROR_OK = 1
	return ExecuteSimpleTaskResult{
		Response:   resp.GetResult(),
		TokensUsed: int(resp.GetUsage().GetTotalTokens() + resp.GetBudget().GetTokensUsed()),
		Success:    ok,
		Error:      resp.GetErrorMessage(),
		ModelUsed:  resp.GetModelUsed(),
		Provider:   resp.GetProvider(),
	}, nil
}

func langGraphWorkerEnabled() bool {
	if os.Getenv("LANGGRAPH_WORKER_ENABLED") == "0" {
		return false
	}
	return strategyworker.Enabled()
}
