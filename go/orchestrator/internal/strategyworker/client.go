package strategyworker

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	commonpb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/common"
	strategypb "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/pb/strategy"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/structpb"
)

const defaultAddr = "langgraph-worker:50053"

func Enabled() bool {
	if v := strings.TrimSpace(os.Getenv("LANGGRAPH_WORKER_ENABLED")); v == "1" || strings.EqualFold(v, "true") {
		return true
	}
	return strings.TrimSpace(os.Getenv("LANGGRAPH_WORKER_ADDR")) != ""
}

func Addr() string {
	if v := strings.TrimSpace(os.Getenv("LANGGRAPH_WORKER_ADDR")); v != "" {
		return v
	}
	return defaultAddr
}

func KindFromMode(mode string) strategypb.StrategyKind {
	switch strings.ToLower(strings.TrimSpace(mode)) {
	case "dag", "complex", "standard":
		return strategypb.StrategyKind_STRATEGY_KIND_DAG
	case "research":
		return strategypb.StrategyKind_STRATEGY_KIND_RESEARCH
	case "swarm", "multi_agent":
		return strategypb.StrategyKind_STRATEGY_KIND_SWARM
	case "simple", "sample", "":
		return strategypb.StrategyKind_STRATEGY_KIND_SAMPLE
	default:
		return strategypb.StrategyKind_STRATEGY_KIND_SAMPLE
	}
}

func HistoryToMessages(history []string) []*strategypb.ConversationMessage {
	out := make([]*strategypb.ConversationMessage, 0, len(history))
	for _, raw := range history {
		role, content := "user", raw
		if strings.HasPrefix(raw, "assistant:") {
			role = "assistant"
			content = strings.TrimSpace(strings.TrimPrefix(raw, "assistant:"))
		} else if strings.HasPrefix(raw, "user:") {
			content = strings.TrimSpace(strings.TrimPrefix(raw, "user:"))
		} else if strings.HasPrefix(raw, "system:") {
			role = "system"
			content = strings.TrimSpace(strings.TrimPrefix(raw, "system:"))
		}
		if content == "" {
			continue
		}
		out = append(out, &strategypb.ConversationMessage{Role: role, Content: content})
	}
	return out
}

type Request struct {
	WorkflowID       string
	TaskID           string
	Query            string
	Mode             string
	UserID           string
	SessionID        string
	Context          map[string]interface{}
	History          []string
	TokenBudget      int32
	RequireApproval  bool
	AvailableTools   []string
}

func withClient(ctx context.Context, fn func(strategypb.StrategyWorkerClient) error) error {
	dialTimeout := 10 * time.Second
	if deadline, ok := ctx.Deadline(); ok {
		if remain := time.Until(deadline); remain > 0 && remain < dialTimeout {
			dialTimeout = remain
		}
	}
	dialCtx, cancel := context.WithTimeout(ctx, dialTimeout)
	defer cancel()
	conn, err := grpc.DialContext(dialCtx, Addr(), grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithBlock())
	if err != nil {
		return err
	}
	defer conn.Close()
	return fn(strategypb.NewStrategyWorkerClient(conn))
}

func BuildRunRequest(in Request) (*strategypb.RunStrategyRequest, error) {
	ctxStruct, err := structpb.NewStruct(sanitizeContext(in.Context))
	if err != nil {
		ctxStruct, _ = structpb.NewStruct(map[string]interface{}{})
	}
	return &strategypb.RunStrategyRequest{
		Metadata: &commonpb.TaskMetadata{
			TaskId:      firstNonEmpty(in.TaskID, in.WorkflowID),
			UserId:      in.UserID,
			SessionId:   in.SessionID,
			TokenBudget: float64(in.TokenBudget),
		},
		WorkflowId: in.WorkflowID,
		Query:      in.Query,
		Strategy:   KindFromMode(in.Mode),
		Context:    ctxStruct,
		Session: &strategypb.SessionPayload{
			SessionId: in.SessionID,
			UserId:    in.UserID,
			History:   HistoryToMessages(in.History),
		},
		Budget:           &strategypb.Budget{TokenBudget: in.TokenBudget},
		RequireApproval:  in.RequireApproval,
		AvailableTools:   in.AvailableTools,
	}, nil
}

func sanitizeContext(in map[string]interface{}) map[string]interface{} {
	if in == nil {
		return map[string]interface{}{}
	}
	out := make(map[string]interface{}, len(in))
	for k, v := range in {
		if conv, ok := toStructValue(v); ok {
			out[k] = conv
		}
	}
	return out
}

func toStructValue(v interface{}) (interface{}, bool) {
	switch t := v.(type) {
	case nil, bool, string, float64:
		return t, true
	case int:
		return float64(t), true
	case int32:
		return float64(t), true
	case int64:
		return float64(t), true
	case []interface{}:
		arr := make([]interface{}, 0, len(t))
		for _, item := range t {
			if conv, ok := toStructValue(item); ok {
				arr = append(arr, conv)
			}
		}
		return arr, true
	case []map[string]interface{}:
		arr := make([]interface{}, 0, len(t))
		for _, item := range t {
			if conv, ok := toStructValue(item); ok {
				arr = append(arr, conv)
			}
		}
		return arr, true
	case map[string]interface{}:
		m := make(map[string]interface{}, len(t))
		for k, item := range t {
			if conv, ok := toStructValue(item); ok {
				m[k] = conv
			}
		}
		return m, true
	default:
		return fmt.Sprint(v), true
	}
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}

func Run(ctx context.Context, in Request) (*strategypb.RunStrategyResponse, error) {
	req, err := BuildRunRequest(in)
	if err != nil {
		return nil, err
	}
	var resp *strategypb.RunStrategyResponse
	err = withClient(ctx, func(client strategypb.StrategyWorkerClient) error {
		var callErr error
		resp, callErr = client.RunStrategy(ctx, req)
		return callErr
	})
	return resp, err
}

func Cancel(ctx context.Context, workflowID, taskID, reason string) error {
	if ctx.Err() != nil {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
	}
	return withClient(ctx, func(client strategypb.StrategyWorkerClient) error {
		_, err := client.Cancel(ctx, &strategypb.CancelRequest{
			WorkflowId: workflowID,
			TaskId:     taskID,
			Reason:     reason,
		})
		return err
	})
}

func Approve(ctx context.Context, workflowID, taskID, approvalID string, approved bool, comment, reviewer string) (*strategypb.ApproveDecisionResponse, error) {
	var resp *strategypb.ApproveDecisionResponse
	err := withClient(ctx, func(client strategypb.StrategyWorkerClient) error {
		var callErr error
		resp, callErr = client.ApproveDecision(ctx, &strategypb.ApproveDecisionRequest{
			WorkflowId:  workflowID,
			TaskId:      taskID,
			ApprovalId:  approvalID,
			Approved:    approved,
			Comment:     comment,
			Reviewer:    reviewer,
		})
		return callErr
	})
	return resp, err
}

func InjectSession(ctx context.Context, workflowID, taskID string, session *strategypb.SessionPayload) (*strategypb.InjectSessionContextResponse, error) {
	var resp *strategypb.InjectSessionContextResponse
	err := withClient(ctx, func(client strategypb.StrategyWorkerClient) error {
		var callErr error
		resp, callErr = client.InjectSessionContext(ctx, &strategypb.InjectSessionContextRequest{
			WorkflowId: workflowID,
			TaskId:     taskID,
			Session:    session,
		})
		return callErr
	})
	return resp, err
}
