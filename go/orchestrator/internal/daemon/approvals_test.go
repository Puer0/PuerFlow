package daemon

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func setupApprovalManager(t *testing.T) (*ApprovalManager, *miniredis.Miniredis) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)
	rc := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	return NewApprovalManager(rc), mr
}

func TestApprovalManager_StoreAndGet(t *testing.T) {
	am, _ := setupApprovalManager(t)
	ctx := context.Background()

	approval := PendingApproval{
		RequestID: "req-123",
		ConnID:    "conn-abc",
		TenantID:  "tenant-1",
		UserID:    "user-1",
		Agent:     "my-agent",
		Tool:      "bash",
		Args:      `{"cmd": "ls"}`,
		CreatedAt: "2026-03-12T00:00:00Z",
	}

	if err := am.Store(ctx, approval); err != nil {
		t.Fatal(err)
	}

	got, err := am.Get(ctx, "req-123")
	if err != nil {
		t.Fatal(err)
	}

	if got.RequestID != "req-123" || got.ConnID != "conn-abc" || got.Tool != "bash" {
		t.Errorf("got unexpected approval: %+v", got)
	}
}

func TestApprovalManager_Resolve_FirstWins(t *testing.T) {
	am, _ := setupApprovalManager(t)
	ctx := context.Background()

	approval := PendingApproval{
		RequestID: "req-456",
		ConnID:    "conn-abc",
		TenantID:  "tenant-1",
		UserID:    "user-1",
		Agent:     "my-agent",
		Tool:      "file_write",
	}

	if err := am.Store(ctx, approval); err != nil {
		t.Fatal(err)
	}

	// First resolve should succeed
	got, err := am.Resolve(ctx, "req-456")
	if err != nil {
		t.Fatal(err)
	}
	if got.RequestID != "req-456" {
		t.Errorf("expected req-456, got %s", got.RequestID)
	}

	// Second resolve should return ErrApprovalNotFound (already resolved)
	_, err = am.Resolve(ctx, "req-456")
	if err != ErrApprovalNotFound {
		t.Errorf("expected ErrApprovalNotFound, got %v", err)
	}
}

func TestApprovalManager_Resolve_NotFound(t *testing.T) {
	am, _ := setupApprovalManager(t)
	ctx := context.Background()

	_, err := am.Resolve(ctx, "nonexistent")
	if err != ErrApprovalNotFound {
		t.Errorf("expected ErrApprovalNotFound, got %v", err)
	}
}

func TestApprovalManager_UpdateChannelMsg(t *testing.T) {
	am, _ := setupApprovalManager(t)
	ctx := context.Background()

	approval := PendingApproval{
		RequestID: "req-789",
		ConnID:    "conn-abc",
		TenantID:  "tenant-1",
		UserID:    "user-1",
		Agent:     "my-agent",
		Tool:      "bash",
	}

	if err := am.Store(ctx, approval); err != nil {
		t.Fatal(err)
	}

	if err := am.UpdateChannelMsg(ctx, "req-789", "ch-1", "slack-ts-123"); err != nil {
		t.Fatal(err)
	}
	if err := am.UpdateChannelMsg(ctx, "req-789", "ch-2", "line-msg-456"); err != nil {
		t.Fatal(err)
	}

	got, err := am.Get(ctx, "req-789")
	if err != nil {
		t.Fatal(err)
	}

	if len(got.ChannelMsgs) != 2 {
		t.Errorf("expected 2 channel msgs, got %d", len(got.ChannelMsgs))
	}
	if got.ChannelMsgs["ch-1"] != "slack-ts-123" {
		t.Errorf("expected slack-ts-123, got %s", got.ChannelMsgs["ch-1"])
	}
	if got.ChannelMsgs["ch-2"] != "line-msg-456" {
		t.Errorf("expected line-msg-456, got %s", got.ChannelMsgs["ch-2"])
	}
}

func TestApprovalManager_CancelByConn(t *testing.T) {
	am, _ := setupApprovalManager(t)
	ctx := context.Background()

	// Store two approvals for same connection
	for _, id := range []string{"req-a", "req-b"} {
		am.Store(ctx, PendingApproval{
			RequestID: id,
			ConnID:    "conn-to-cancel",
			TenantID:  "tenant-1",
			UserID:    "user-1",
		})
	}
	// Store one for a different connection
	am.Store(ctx, PendingApproval{
		RequestID: "req-c",
		ConnID:    "conn-keep",
		TenantID:  "tenant-1",
		UserID:    "user-1",
	})

	cancelled, err := am.CancelByConn(ctx, "conn-to-cancel")
	if err != nil {
		t.Fatal(err)
	}
	if len(cancelled) != 2 {
		t.Errorf("expected 2 cancelled, got %d", len(cancelled))
	}

	// req-c should still exist
	got, err := am.Get(ctx, "req-c")
	if err != nil {
		t.Fatal(err)
	}
	if got.ConnID != "conn-keep" {
		t.Errorf("req-c should be preserved, got %+v", got)
	}

	// req-a and req-b should be gone
	_, err = am.Get(ctx, "req-a")
	if err != ErrApprovalNotFound {
		t.Errorf("req-a should be gone, got %v", err)
	}
}
