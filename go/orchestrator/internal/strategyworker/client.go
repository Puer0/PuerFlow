package strategyworker

import (
	"context"
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
	WorkflowID string
	TaskID     string
	Query      string
	Mode       string
	UserID     string
	SessionID  string
	Context    map[string]interface{}
	History    []string
	TokenBudget int32
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
		Budget: &strategypb.Budget{TokenBudget: in.TokenBudget},
	}, nil
}

func sanitizeContext(in map[string]interface{}) map[string]interface{} {
	if in == nil {
		return map[string]interface{}{}
	}
	out := make(map[string]interface{}, len(in))
	for k, v := range in {
		switch v.(type) {
		case string, bool, float64, int, int32, int64, nil:
			out[k] = v
		}
	}
	return out
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
	dialCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	conn, err := grpc.DialContext(dialCtx, Addr(), grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithBlock())
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	req, err := BuildRunRequest(in)
	if err != nil {
		return nil, err
	}
	client := strategypb.NewStrategyWorkerClient(conn)
	return client.RunStrategy(ctx, req)
}
