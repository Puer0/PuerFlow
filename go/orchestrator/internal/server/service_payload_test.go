package server

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/workflows"
	"github.com/stretchr/testify/assert"
	"go.temporal.io/api/serviceerror"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestEnforceTaskInputPayloadLimitTrimsHistory(t *testing.T) {
	history := make([]workflows.Message, 0, 70)
	for i := 0; i < 70; i++ {
		history = append(history, workflows.Message{
			Role:      "assistant",
			Content:   fmt.Sprintf("msg-%03d-%s", i, strings.Repeat("x", 40000)),
			Timestamp: time.Unix(int64(i), 0),
		})
	}

	conversationHistory := []interface{}{
		map[string]interface{}{
			"role":    "assistant",
			"content": "keep this context intact",
		},
	}

	input := workflows.TaskInput{
		Query:     "latest query",
		UserID:    "user-1",
		SessionID: "session-1",
		Context: map[string]interface{}{
			"conversation_history": conversationHistory,
		},
		History: history,
		SessionCtx: map[string]interface{}{
			"last_response": "short summary",
		},
	}

	initialSize, err := estimateTaskInputPayloadSizeBytes(input)
	assert.NoError(t, err)
	assert.Greater(t, initialSize, taskInputPreflightLimitBytes)

	result, err := enforceTaskInputPayloadLimit(&input, taskInputPreflightLimitBytes)
	assert.NoError(t, err)
	assert.Equal(t, initialSize, result.InitialSizeBytes)
	assert.Greater(t, result.TrimmedMessages, 0)
	assert.Less(t, len(input.History), len(history))
	assert.LessOrEqual(t, result.FinalSizeBytes, taskInputPreflightLimitBytes)
	assert.Equal(t, conversationHistory, input.Context["conversation_history"])
	assert.Equal(t, history[result.TrimmedMessages].Content, input.History[0].Content)
	assert.Equal(t, history[len(history)-1].Content, input.History[len(input.History)-1].Content)
}

func TestEnforceTaskInputPayloadLimitRejectsOversizedNonHistoryPayload(t *testing.T) {
	input := workflows.TaskInput{
		Query:   strings.Repeat("q", taskInputPreflightLimitBytes),
		UserID:  "user-1",
		Context: map[string]interface{}{"conversation_history": []interface{}{}},
	}

	result, err := enforceTaskInputPayloadLimit(&input, taskInputPreflightLimitBytes)
	assert.Error(t, err)
	assert.Zero(t, result.TrimmedMessages)
	assert.Greater(t, result.FinalSizeBytes, taskInputPreflightLimitBytes)
	assert.Contains(t, err.Error(), "preflight limit")
}

func TestWorkflowStartStatusErrorPreservesDeadline(t *testing.T) {
	err := workflowStartStatusError(context.DeadlineExceeded)
	st, ok := status.FromError(err)
	if !ok {
		t.Fatal("expected gRPC status error")
	}

	assert.Equal(t, codes.DeadlineExceeded, st.Code())
	assert.Contains(t, st.Message(), "context deadline exceeded")
}

func TestWorkflowStartStatusErrorPreservesTemporalInvalidArgument(t *testing.T) {
	err := workflowStartStatusError(serviceerror.NewInvalidArgument("blob size exceeds limit"))
	st, ok := status.FromError(err)
	if !ok {
		t.Fatal("expected gRPC status error")
	}

	assert.Equal(t, codes.InvalidArgument, st.Code())
	assert.Contains(t, st.Message(), "blob size exceeds limit")
}
