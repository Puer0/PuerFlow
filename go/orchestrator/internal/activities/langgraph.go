package activities

import (
	"context"
	"os"
	"strings"
	"time"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/strategyworker"
	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
	"go.temporal.io/sdk/activity"
	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type LangGraphTaskInput struct {
	ExecuteSimpleTaskInput
	Mode            string `json:"mode,omitempty"`
	RequireApproval bool   `json:"require_approval,omitempty"`
	TenantID        string `json:"tenant_id,omitempty"`
}

type LangGraphTaskResult struct {
	Used bool `json:"used"`
	ExecuteSimpleTaskResult
}

type CancelLangGraphInput struct {
	WorkflowID string `json:"workflow_id"`
	TaskID     string `json:"task_id,omitempty"`
	Reason     string `json:"reason,omitempty"`
}

type ApproveLangGraphInput struct {
	WorkflowID string `json:"workflow_id"`
	TaskID     string `json:"task_id,omitempty"`
	ApprovalID string `json:"approval_id,omitempty"`
	Approved   bool   `json:"approved"`
	Comment    string `json:"comment,omitempty"`
	Reviewer   string `json:"reviewer,omitempty"`
}

func ExecuteLangGraphIfEnabled(ctx context.Context, input LangGraphTaskInput) (LangGraphTaskResult, error) {
	if !langGraphWorkerEnabled() {
		return LangGraphTaskResult{Used: false}, nil
	}
	simple := input.ExecuteSimpleTaskInput
	if input.Mode != "" {
		simple.Mode = input.Mode
	}
	simple.RequireApproval = input.RequireApproval
	simple.TenantID = input.TenantID
	res, err := ExecuteLangGraphStrategy(ctx, simple)
	return LangGraphTaskResult{Used: true, ExecuteSimpleTaskResult: res}, err
}

func ExecuteLangGraphStrategy(ctx context.Context, input ExecuteSimpleTaskInput) (ExecuteSimpleTaskResult, error) {
	logger := activity.GetLogger(ctx)
	mode := input.Mode
	if mode == "" {
		mode = "simple"
	}
	logger.Info("ExecuteLangGraphStrategy started",
		"query", input.Query,
		"session_id", input.SessionID,
		"workflow_id", input.ParentWorkflowID,
		"mode", mode,
	)

	merged := make(map[string]interface{})
	for k, v := range input.Context {
		merged[k] = v
	}
	for k, v := range input.SessionCtx {
		merged[k] = v
	}
	if input.UserID != "" {
		if _, exists := merged["user_id"]; !exists {
			merged["user_id"] = input.UserID
		}
	}

	if input.SessionID != "" {
		mem, memErr := FetchHierarchicalMemory(ctx, FetchHierarchicalMemoryInput{
			Query:        input.Query,
			SessionID:    input.SessionID,
			TenantID:     input.TenantID,
			RecentTopK:   5,
			SemanticTopK: 5,
			Threshold:    0.75,
		})
		if memErr != nil {
			logger.Warn("hierarchical memory fetch failed", "error", memErr.Error())
		} else if len(mem.Items) > 0 {
			merged["agent_memory"] = mem.Items
		}
	}

	tokenBudget := int32(0)
	if merged != nil {
		if v, ok := merged["token_budget"].(float64); ok {
			tokenBudget = int32(v)
		}
	}

	callCtx, cancel := context.WithTimeout(ctx, 10*time.Minute)
	defer cancel()

	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-ctx.Done():
			cancelCtx, stop := context.WithTimeout(context.Background(), 5*time.Second)
			defer stop()
			_ = strategyworker.Cancel(cancelCtx, input.ParentWorkflowID, input.ParentWorkflowID, "temporal cancelled")
		case <-done:
		}
	}()

	resp, err := strategyworker.Run(callCtx, strategyworker.Request{
		WorkflowID:      input.ParentWorkflowID,
		TaskID:          input.ParentWorkflowID,
		Query:           input.Query,
		Mode:            mode,
		UserID:          input.UserID,
		SessionID:       input.SessionID,
		Context:         merged,
		History:         input.History,
		TokenBudget:     tokenBudget,
		RequireApproval: input.RequireApproval,
		AvailableTools:  input.SuggestedTools,
	})
	if err != nil {
		if st, ok := status.FromError(err); ok && st.Code() == codes.Canceled {
			return ExecuteSimpleTaskResult{Success: false, Error: "cancelled"}, err
		}
		zap.L().Error("LangGraph worker call failed", zap.Error(err))
		return ExecuteSimpleTaskResult{Success: false, Error: err.Error()}, err
	}

	code := resp.GetErrorCode()
	ok := code == strategypb.StrategyErrorCode_STRATEGY_ERROR_OK || (code == strategypb.StrategyErrorCode_STRATEGY_ERROR_UNSPECIFIED && resp.GetResult() != "")
	result := ExecuteSimpleTaskResult{
		Response:   resp.GetResult(),
		TokensUsed: int(resp.GetUsage().GetTotalTokens() + resp.GetBudget().GetTokensUsed()),
		Success:    ok,
		Error:      resp.GetErrorMessage(),
		ModelUsed:  resp.GetModelUsed(),
		Provider:   resp.GetProvider(),
	}
	switch code {
	case strategypb.StrategyErrorCode_STRATEGY_ERROR_CANCELLED:
		result.Success = false
		if result.Error == "" {
			result.Error = "cancelled"
		}
		return result, status.Error(codes.Canceled, result.Error)
	case strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED:
		result.Success = false
		if result.Error == "" {
			result.Error = "budget exceeded"
		}
		return result, status.Error(codes.ResourceExhausted, result.Error)
	}
	if resp.GetBudget().GetExceeded() {
		result.Success = false
		if result.Error == "" {
			result.Error = "budget exceeded"
		}
		return result, status.Error(codes.ResourceExhausted, result.Error)
	}
	return result, nil
}

func CancelLangGraphStrategy(ctx context.Context, input CancelLangGraphInput) error {
	if strings.TrimSpace(input.WorkflowID) == "" {
		return nil
	}
	reason := input.Reason
	if reason == "" {
		reason = "workflow cancelled"
	}
	return strategyworker.Cancel(ctx, input.WorkflowID, input.TaskID, reason)
}

func ApproveLangGraphDecision(ctx context.Context, input ApproveLangGraphInput) error {
	if strings.TrimSpace(input.WorkflowID) == "" {
		return nil
	}
	_, err := strategyworker.Approve(ctx, input.WorkflowID, input.TaskID, input.ApprovalID, input.Approved, input.Comment, input.Reviewer)
	return err
}

func langGraphWorkerEnabled() bool {
	if os.Getenv("LANGGRAPH_WORKER_ENABLED") == "0" {
		return false
	}
	return strategyworker.Enabled()
}
