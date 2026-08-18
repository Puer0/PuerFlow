package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	authpkg "github.com/Kocoro-lab/Shannon/go/orchestrator/internal/auth"
	"github.com/google/uuid"
	"go.uber.org/zap/zaptest"
)

// --- Mocks ---

type mockAuthService struct {
	apiKeys    map[string]*authpkg.UserContext
	jwtTokens  map[string]*authpkg.UserContext
}

func (m *mockAuthService) ValidateAPIKey(ctx context.Context, apiKey string) (*authpkg.UserContext, error) {
	if u, ok := m.apiKeys[apiKey]; ok {
		return u, nil
	}
	return nil, assertErr("invalid api key")
}

func (m *mockAuthService) ValidateAccessToken(ctx context.Context, token string) (*authpkg.UserContext, error) {
	if u, ok := m.jwtTokens[token]; ok {
		return u, nil
	}
	return nil, assertErr("invalid token")
}

type assertErr string

func (e assertErr) Error() string { return string(e) }

func okHandler(t *testing.T) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
}

// --- Auth tests ---

func TestAuth_NoQueryParamAccepted(t *testing.T) {
	os.Setenv("GATEWAY_SKIP_AUTH", "0")
	t.Cleanup(func() { os.Unsetenv("GATEWAY_SKIP_AUTH") })
	logger := zaptest.NewLogger(t)
	uid := uuid.New()
	tid := uuid.New()
	mw := NewAuthMiddleware(&mockAuthService{apiKeys: map[string]*authpkg.UserContext{
		"good": {UserID: uid, TenantID: tid, IsAPIKey: true, TokenType: "api_key"},
	}}, logger)

	handler := mw.Middleware(okHandler(t))

	// Only query param present -> unauthorized
	req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks?api_key=good", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 when using api_key query param, got %d", rec.Code)
	}
}

func TestAuth_QueryParamAcceptedForStreaming(t *testing.T) {
	os.Setenv("GATEWAY_SKIP_AUTH", "0")
	t.Cleanup(func() { os.Unsetenv("GATEWAY_SKIP_AUTH") })
	logger := zaptest.NewLogger(t)
	uid := uuid.New()
	tid := uuid.New()
	jwtToken := "jwt.header.payload"
	mw := NewAuthMiddleware(&mockAuthService{
		apiKeys: map[string]*authpkg.UserContext{
			"good": {UserID: uid, TenantID: tid, IsAPIKey: true, TokenType: "api_key"},
		},
		jwtTokens: map[string]*authpkg.UserContext{
			jwtToken: {UserID: uid, TenantID: tid, IsAPIKey: false, TokenType: "jwt"},
		},
	}, logger)

	handler := mw.Middleware(okHandler(t))

	// SSE endpoint: accept token query param (JWT)
	{
		req := httptest.NewRequest(http.MethodGet, "/api/v1/stream/sse?workflow_id=task-abc&token="+jwtToken, nil)
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 when using token query param on streaming endpoint, got %d", rec.Code)
		}
	}

	// SSE endpoint: accept api_key query param
	{
		req := httptest.NewRequest(http.MethodGet, "/api/v1/stream/sse?workflow_id=task-abc&api_key=good", nil)
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 when using api_key query param on streaming endpoint, got %d", rec.Code)
		}
	}

	// Non-streaming endpoint: reject token query param
	{
		req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/task-abc/events?token="+jwtToken, nil)
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusUnauthorized {
			t.Fatalf("expected 401 when using token query param on non-streaming endpoint, got %d", rec.Code)
		}
	}
}

func TestAuth_HeaderAndBearerAccepted(t *testing.T) {
	os.Setenv("GATEWAY_SKIP_AUTH", "0")
	t.Cleanup(func() { os.Unsetenv("GATEWAY_SKIP_AUTH") })
	logger := zaptest.NewLogger(t)
	uid := uuid.New()
	tid := uuid.New()
	jwtToken := "jwt.header.payload"
	mw := NewAuthMiddleware(&mockAuthService{
		apiKeys: map[string]*authpkg.UserContext{
			"good": {UserID: uid, TenantID: tid, IsAPIKey: true, TokenType: "api_key"},
		},
		jwtTokens: map[string]*authpkg.UserContext{
			jwtToken: {UserID: uid, TenantID: tid, IsAPIKey: false, TokenType: "jwt"},
		},
	}, logger)

	// X-API-Key
	{
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.Header.Set("X-API-Key", "good")
		rec := httptest.NewRecorder()
		mw.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 with X-API-Key, got %d", rec.Code)
		}
	}
	// Authorization: Bearer
	{
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.Header.Set("Authorization", "Bearer good")
		rec := httptest.NewRecorder()
		mw.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 with Bearer, got %d", rec.Code)
		}
	}

	// Authorization: Bearer (JWT)
	{
		req := httptest.NewRequest(http.MethodGet, "/x", nil)
		req.Header.Set("Authorization", "Bearer "+jwtToken)
		rec := httptest.NewRecorder()
		mw.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 with Bearer JWT, got %d", rec.Code)
		}
	}
}

func TestAuth_SkipAuthEnv(t *testing.T) {
	os.Setenv("GATEWAY_SKIP_AUTH", "1")
	os.Setenv("ENVIRONMENT", "test")
	t.Cleanup(func() {
		os.Unsetenv("GATEWAY_SKIP_AUTH")
		os.Unsetenv("ENVIRONMENT")
	})
	logger := zaptest.NewLogger(t)
	mw := NewAuthMiddleware(&mockAuthService{apiKeys: map[string]*authpkg.UserContext{}, jwtTokens: map[string]*authpkg.UserContext{}}, logger)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	mw.Middleware(okHandler(t)).ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 when skipping auth, got %d", rec.Code)
	}
}

// --- Validation tests ---

func TestValidation_ListTasksInvalidLimitOffset(t *testing.T) {
	logger := zaptest.NewLogger(t)
	vm := NewValidationMiddleware(logger)

	// invalid limit
	{
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks?limit=abc", nil)
		vm.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 for invalid limit, got %d", rec.Code)
		}
	}
	// invalid offset
	{
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks?offset=-1", nil)
		vm.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 for invalid offset, got %d", rec.Code)
		}
	}
}

func TestValidation_PathAndSSEParams(t *testing.T) {
	logger := zaptest.NewLogger(t)
	vm := NewValidationMiddleware(logger)

	// invalid id
	{
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/%20/events", nil) // space in id
		vm.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 for invalid id, got %d", rec.Code)
		}
	}

	// missing workflow_id
	{
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/api/v1/stream/sse", nil)
		vm.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400 for missing workflow_id, got %d", rec.Code)
		}
	}

	// valid workflow_id
	{
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/api/v1/stream/sse?workflow_id=task-abc_123", nil)
		vm.Middleware(okHandler(t)).ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 for valid workflow_id, got %d", rec.Code)
		}
	}
}
