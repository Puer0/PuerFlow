package activities

import (
	"context"
	"os"
	"strings"
	"time"

	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/strategyworker"
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
	Failover       bool   `json:"failover,omitempty"`
	OriginalMode   string `json:"original_mode,omitempty"`
	FailoverMode   string `json:"failover_mode,omitempty"`
	FailoverReason string `json:"failover_reason,omitempty"`
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

type langGraphCall struct {
	ExecuteSimpleTaskResult
	ErrorCode    strategypb.StrategyErrorCode
	FailoverHint *strategypb.FailoverHint
}

var (
	langGraphRun  = strategyworker.Run
	langGraphHint = strategyworker.GetFailoverHint
)

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
	mode := simple.Mode
	if mode == "" {
		mode = "simple"
		simple.Mode = mode
	}

	call, err := executeLangGraphOnce(ctx, simple)
	out := LangGraphTaskResult{Used: true, ExecuteSimpleTaskResult: call.ExecuteSimpleTaskResult}
	if langGraphSucceeded(call, err) {
		return out, nil
	}
	if !strategyworker.EligibleForFailover(mode, call.ErrorCode, err) {
		return out, err
	}

	hint := call.FailoverHint
	if hint == nil {
		resp, hintErr := langGraphHint(ctx, simple.ParentWorkflowID, simple.ParentWorkflowID, call.ErrorCode, mode)
		if hintErr != nil {
			activity.GetLogger(ctx).Warn("GetFailoverHint failed", "error", hintErr.Error(), "mode", mode)
		} else {
			hint = resp.GetHint()
		}
	}
	dec := strategyworker.DecideFailover(mode, hint)
	if !dec.Should {
		return out, err
	}

	activity.GetLogger(ctx).Info("LangGraph failover",
		"from", mode,
		"to", dec.Mode,
		"reason", dec.Reason,
	)
	fallback := simple
	fallback.Mode = dec.Mode
	fb, fbErr := executeLangGraphOnce(ctx, fallback)
	fb.TokensUsed += call.TokensUsed
	out = LangGraphTaskResult{
		Used:                    true,
		ExecuteSimpleTaskResult: fb.ExecuteSimpleTaskResult,
		Failover:                true,
		OriginalMode:            mode,
		FailoverMode:            dec.Mode,
		FailoverReason:          dec.Reason,
	}
	if langGraphSucceeded(fb, fbErr) {
		return out, nil
	}
	if fbErr != nil {
		return out, fbErr
	}
	return out, err
}

func ExecuteLangGraphStrategy(ctx context.Context, input ExecuteSimpleTaskInput) (ExecuteSimpleTaskResult, error) {
	call, err := executeLangGraphOnce(ctx, input)
	return call.ExecuteSimpleTaskResult, err
}

func executeLangGraphOnce(ctx context.Context, input ExecuteSimpleTaskInput) (langGraphCall, error) {
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

	attachLangGraphModelRouting(mode, merged)

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

	resp, err := langGraphRun(callCtx, strategyworker.Request{
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
		code := strategyworker.ErrorCodeFromRPC(err)
		if st, ok := status.FromError(err); ok && st.Code() == codes.Canceled {
			return langGraphCall{
				ExecuteSimpleTaskResult: ExecuteSimpleTaskResult{Success: false, Error: "cancelled"},
				ErrorCode:               code,
			}, err
		}
		zap.L().Error("LangGraph worker call failed", zap.Error(err))
		return langGraphCall{
			ExecuteSimpleTaskResult: ExecuteSimpleTaskResult{Success: false, Error: err.Error()},
			ErrorCode:               code,
		}, err
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
	call := langGraphCall{
		ExecuteSimpleTaskResult: result,
		ErrorCode:               code,
		FailoverHint:            resp.GetFailover(),
	}
	switch code {
	case strategypb.StrategyErrorCode_STRATEGY_ERROR_CANCELLED:
		call.Success = false
		if call.Error == "" {
			call.Error = "cancelled"
		}
		return call, status.Error(codes.Canceled, call.Error)
	case strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED:
		call.Success = false
		if call.Error == "" {
			call.Error = "budget exceeded"
		}
		return call, status.Error(codes.ResourceExhausted, call.Error)
	}
	if resp.GetBudget().GetExceeded() {
		call.Success = false
		call.ErrorCode = strategypb.StrategyErrorCode_STRATEGY_ERROR_BUDGET_EXCEEDED
		if call.Error == "" {
			call.Error = "budget exceeded"
		}
		return call, status.Error(codes.ResourceExhausted, call.Error)
	}
	return call, nil
}

func langGraphSucceeded(call langGraphCall, err error) bool {
	return err == nil && call.Success
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

func attachLangGraphModelRouting(mode string, merged map[string]interface{}) {
	if merged == nil {
		return
	}
	if _, exists := merged["model_tier"]; !exists {
		merged["model_tier"] = defaultLangGraphModelTier(mode)
	}
	if _, exists := merged["synthesis_model_tier"]; !exists {
		merged["synthesis_model_tier"] = "large"
	}
	if _, exists := merged["utility_model_tier"]; !exists {
		merged["utility_model_tier"] = "small"
	}
}

func defaultLangGraphModelTier(mode string) string {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "simple", "sample":
		return "small"
	default:
		return "medium"
	}
}

func langGraphWorkerEnabled() bool {
	if os.Getenv("LANGGRAPH_WORKER_ENABLED") == "0" {
		return false
	}
	return strategyworker.Enabled()
}
