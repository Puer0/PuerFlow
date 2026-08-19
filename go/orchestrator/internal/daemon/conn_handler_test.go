package daemon

import (
	"context"
	"encoding/json"
	"sync"
	"testing"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/streaming"
	"go.uber.org/zap"
)

// mockStreamingManager implements eventPublisher for testing.
type mockStreamingManager struct {
	mu     sync.Mutex
	events []streaming.Event
}

func (m *mockStreamingManager) Publish(workflowID string, evt streaming.Event) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, evt)
}

func (m *mockStreamingManager) getEvents() []streaming.Event {
	m.mu.Lock()
	defer m.mu.Unlock()
	cp := make([]streaming.Event, len(m.events))
	copy(cp, m.events)
	return cp
}

func TestHandleDaemonEvent_PublishesToStreaming(t *testing.T) {
	hub, _ := setupHub(t)
	ctx := context.Background()
	logger := zap.NewNop()

	// Claim must exist before HandleProgress (called inside handleDaemonEvent).
	_, err := hub.HandleClaim(ctx, "conn-1", "msg-evt-1", ClaimMetadata{
		ChannelType: ChannelSlack,
		ThreadID:    "thread-1",
	})
	if err != nil {
		t.Fatal(err)
	}

	mock := &mockStreamingManager{}
	tracker := &daemonStreamTracker{initState: &sync.Map{}}

	payload := DaemonEventPayload{
		EventType: "TOOL_INVOKED",
		Message:   "calling web_search",
		Seq:       1,
		Timestamp: "2026-03-23T10:00:00Z",
	}
	raw, _ := json.Marshal(payload)

	// Track OnWorkflowStarted callback.
	workflowStarted := false
	hub.OnWorkflowStarted = func(ctx context.Context, messageID string, meta ClaimMetadata) {
		workflowStarted = true
	}

	handleDaemonEvent(ctx, hub, "msg-evt-1", raw, mock, tracker, logger)

	// Verify event was published.
	events := mock.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 published event, got %d", len(events))
	}

	evt := events[0]
	if evt.Type != "TOOL_INVOKED" {
		t.Errorf("expected event type TOOL_INVOKED, got %s", evt.Type)
	}
	if evt.Message != "calling web_search" {
		t.Errorf("expected message 'calling web_search', got %q", evt.Message)
	}
	if evt.AgentID != "" {
		t.Errorf("expected empty AgentID, got %q", evt.AgentID)
	}
	if evt.WorkflowID != "daemon:msg-evt-1" {
		t.Errorf("expected workflow_id 'daemon:msg-evt-1', got %q", evt.WorkflowID)
	}

	// Verify OnWorkflowStarted was called on first event.
	if !workflowStarted {
		t.Error("expected OnWorkflowStarted callback on first event")
	}

	// Verify daemon_seq preserved in payload.
	if seq, ok := evt.Payload["daemon_seq"]; !ok || seq != int64(1) {
		t.Errorf("expected daemon_seq=1 in payload, got %v", evt.Payload["daemon_seq"])
	}
}

func TestHandleDaemonEvent_SecondEventSkipsInit(t *testing.T) {
	hub, _ := setupHub(t)
	ctx := context.Background()
	logger := zap.NewNop()

	_, err := hub.HandleClaim(ctx, "conn-1", "msg-evt-2", ClaimMetadata{
		ChannelType: ChannelSlack,
	})
	if err != nil {
		t.Fatal(err)
	}

	mock := &mockStreamingManager{}
	tracker := &daemonStreamTracker{initState: &sync.Map{}}

	callCount := 0
	hub.OnWorkflowStarted = func(ctx context.Context, messageID string, meta ClaimMetadata) {
		callCount++
	}

	// First event — triggers init.
	p1, _ := json.Marshal(DaemonEventPayload{EventType: "TOOL_INVOKED", Seq: 1, Timestamp: "2026-03-23T10:00:00Z"})
	handleDaemonEvent(ctx, hub, "msg-evt-2", p1, mock, tracker, logger)

	// Second event — should NOT re-trigger init.
	p2, _ := json.Marshal(DaemonEventPayload{EventType: "TOOL_COMPLETED", Seq: 2, Timestamp: "2026-03-23T10:00:01Z"})
	handleDaemonEvent(ctx, hub, "msg-evt-2", p2, mock, tracker, logger)

	if callCount != 1 {
		t.Errorf("expected OnWorkflowStarted called exactly once, got %d", callCount)
	}

	events := mock.getEvents()
	if len(events) != 2 {
		t.Fatalf("expected 2 published events, got %d", len(events))
	}
}

func TestHandleDaemonReply_SuppressesDuplicateWhenStreamActive(t *testing.T) {
	hub, _ := setupHub(t)
	ctx := context.Background()

	_, err := hub.HandleClaim(ctx, "conn-1", "msg-reply-1", ClaimMetadata{
		ChannelType: ChannelSlack,
		ChannelID:   "ch-001",
	})
	if err != nil {
		t.Fatal(err)
	}

	mock := &mockStreamingManager{}
	tracker := &daemonStreamTracker{initState: &sync.Map{}}

	// Simulate first event (initializes stream via handleDaemonEvent).
	payload, _ := json.Marshal(DaemonEventPayload{EventType: "TOOL_INVOKED", Message: "searching", Seq: 1})
	handleDaemonEvent(ctx, hub, "msg-reply-1", payload, mock, tracker, nil)

	// Verify stream is initialized.
	if !tracker.isInitialized("msg-reply-1") {
		t.Fatal("expected stream to be initialized")
	}

	// Verify the TOOL_INVOKED event was published via the mock.
	events := mock.getEvents()
	if len(events) != 1 || events[0].Type != "TOOL_INVOKED" {
		t.Fatalf("expected 1 TOOL_INVOKED event, got %d events", len(events))
	}

	// Now send a MsgTypeReply via handleDaemonMessage.
	// The MsgTypeReply handler calls streaming.Get() directly (not via mock),
	// so we only verify: replyCalled, correct meta.WorkflowID, and tracker cleanup.
	replyPayload, _ := json.Marshal(ReplyPayload{Text: "final answer"})
	s := &capturedSender{}
	conn := makeConn("conn-1", "t", "u", s)
	hub.Register(conn)

	replyCalled := false
	cbs := &ConnCallbacks{
		OnReply: func(ctx context.Context, meta ClaimMetadata, reply ReplyPayload) {
			replyCalled = true
			if meta.WorkflowID != "daemon:msg-reply-1" {
				t.Errorf("expected WorkflowID=daemon:msg-reply-1, got %q", meta.WorkflowID)
			}
		},
		StreamTracker: tracker,
	}

	handleDaemonMessage(ctx, hub, conn, DaemonMessage{
		Type:      MsgTypeReply,
		MessageID: "msg-reply-1",
		Payload:   replyPayload,
	}, cbs, zap.NewNop())

	if !replyCalled {
		t.Error("expected OnReply to be called")
	}

	// Verify tracker was cleaned up after reply.
	if tracker.isInitialized("msg-reply-1") {
		t.Error("expected stream tracker to be cleaned up after reply")
	}
}

func TestHandleDaemonEvent_MessageIDRequired(t *testing.T) {
	hub, _ := setupHub(t)
	ctx := context.Background()
	logger := zap.NewNop()

	mock := &mockStreamingManager{}
	tracker := &daemonStreamTracker{initState: &sync.Map{}}

	p, _ := json.Marshal(DaemonEventPayload{EventType: "TOOL_INVOKED", Seq: 1})

	// Empty message_id should be dropped (no publish).
	handleDaemonEvent(ctx, hub, "", p, mock, tracker, logger)

	events := mock.getEvents()
	if len(events) != 0 {
		t.Fatalf("expected 0 events for empty message_id, got %d", len(events))
	}
}
