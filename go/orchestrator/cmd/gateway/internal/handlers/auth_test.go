package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestListAPIKeys_RequiresAuth tests that listing keys requires authentication
func TestListAPIKeys_RequiresAuth(t *testing.T) {
	h := &AuthHandler{}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/auth/api-keys", nil)
	rr := httptest.NewRecorder()

	h.ListAPIKeys(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected status %d, got %d", http.StatusUnauthorized, rr.Code)
	}

	var resp ErrorResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	if resp.Message != "Authentication required" {
		t.Errorf("expected error %q, got %q", "Authentication required", resp.Message)
	}
}

// TestCreateKey_RequiresAuth tests that creating keys requires authentication
func TestCreateKey_RequiresAuth(t *testing.T) {
	h := &AuthHandler{}

	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/api-keys", strings.NewReader(`{"name":"Test"}`))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	h.CreateKey(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected status %d, got %d", http.StatusUnauthorized, rr.Code)
	}

	var resp ErrorResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	if resp.Message != "Authentication required" {
		t.Errorf("expected error %q, got %q", "Authentication required", resp.Message)
	}
}

// TestRevokeKey_RequiresAuth tests that revoking keys requires authentication
func TestRevokeKey_RequiresAuth(t *testing.T) {
	h := &AuthHandler{}

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/auth/api-keys/550e8400-e29b-41d4-a716-446655440000", nil)
	req.SetPathValue("id", "550e8400-e29b-41d4-a716-446655440000")
	rr := httptest.NewRecorder()

	h.RevokeKey(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected status %d, got %d", http.StatusUnauthorized, rr.Code)
	}
}

// TestRefreshKey_RequiresAuth tests that refresh-key requires authentication
func TestRefreshKey_RequiresAuth(t *testing.T) {
	h := &AuthHandler{}

	req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/refresh-key", nil)
	rr := httptest.NewRecorder()

	h.RefreshKey(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected status %d, got %d", http.StatusUnauthorized, rr.Code)
	}
}

// TestMe_RequiresAuth tests that /me endpoint requires authentication
func TestMe_RequiresAuth(t *testing.T) {
	h := &AuthHandler{}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/auth/me", nil)
	rr := httptest.NewRecorder()

	h.Me(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected status %d, got %d", http.StatusUnauthorized, rr.Code)
	}
}

// TestAPIKeyInfo_JSONSerialization tests that APIKeyInfo serializes correctly
func TestAPIKeyInfo_JSONSerialization(t *testing.T) {
	info := APIKeyInfo{
		ID:          "550e8400-e29b-41d4-a716-446655440000",
		Name:        "Test Key",
		KeyPrefix:   "sk_abc12",
		Description: nil,
		CreatedAt:   "2025-01-01T00:00:00Z",
		LastUsedAt:  nil,
		IsActive:    true,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	// Verify required fields are present
	jsonStr := string(data)
	requiredFields := []string{"id", "name", "key_prefix", "created_at", "is_active"}
	for _, field := range requiredFields {
		if !strings.Contains(jsonStr, `"`+field+`"`) {
			t.Errorf("missing required field: %s", field)
		}
	}

	// Verify optional fields with nil are omitted
	if strings.Contains(jsonStr, `"description"`) {
		t.Error("nil description should be omitted")
	}
	if strings.Contains(jsonStr, `"last_used_at"`) {
		t.Error("nil last_used_at should be omitted")
	}
}

// TestAPIKeyInfo_WithOptionalFields tests serialization with optional fields set
func TestAPIKeyInfo_WithOptionalFields(t *testing.T) {
	desc := "My test key"
	lastUsed := "2025-01-02T12:00:00Z"
	info := APIKeyInfo{
		ID:          "550e8400-e29b-41d4-a716-446655440000",
		Name:        "Test Key",
		KeyPrefix:   "sk_abc12",
		Description: &desc,
		CreatedAt:   "2025-01-01T00:00:00Z",
		LastUsedAt:  &lastUsed,
		IsActive:    true,
	}

	data, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	jsonStr := string(data)

	// Verify optional fields are present when set
	if !strings.Contains(jsonStr, `"description"`) {
		t.Error("description should be present when set")
	}
	if !strings.Contains(jsonStr, `"last_used_at"`) {
		t.Error("last_used_at should be present when set")
	}
}

// TestCreateAPIKeyResponse_ContainsWarning tests that create response includes warning
func TestCreateAPIKeyResponse_ContainsWarning(t *testing.T) {
	resp := CreateAPIKeyResponse{
		ID:        "550e8400-e29b-41d4-a716-446655440000",
		Name:      "Test Key",
		APIKey:    "sk_test123",
		KeyPrefix: "sk_test1",
		CreatedAt: "2025-01-01T00:00:00Z",
		Warning:   "Store this API key securely. It will not be shown again.",
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	if !strings.Contains(string(data), "warning") {
		t.Error("response should contain warning field")
	}

	if !strings.Contains(string(data), "will not be shown again") {
		t.Error("warning should mention key won't be shown again")
	}
}

// TestListAPIKeysResponse_Structure tests the list response structure
func TestListAPIKeysResponse_Structure(t *testing.T) {
	resp := ListAPIKeysResponse{
		Keys: []APIKeyInfo{
			{
				ID:        "550e8400-e29b-41d4-a716-446655440000",
				Name:      "Key 1",
				KeyPrefix: "sk_abc12",
				CreatedAt: "2025-01-01T00:00:00Z",
				IsActive:  true,
			},
			{
				ID:        "550e8400-e29b-41d4-a716-446655440001",
				Name:      "Key 2",
				KeyPrefix: "sk_def34",
				CreatedAt: "2025-01-02T00:00:00Z",
				IsActive:  false,
			},
		},
		Total: 2,
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	jsonStr := string(data)

	if !strings.Contains(jsonStr, `"keys"`) {
		t.Error("response should contain keys array")
	}
	if !strings.Contains(jsonStr, `"total":2`) {
		t.Error("response should contain total count")
	}
	if !strings.Contains(jsonStr, `"Key 1"`) || !strings.Contains(jsonStr, `"Key 2"`) {
		t.Error("response should contain both keys")
	}
}

// TestRegisterResponse_APIKeyForNewUser tests that api_key is present in response
func TestRegisterResponse_APIKeyField(t *testing.T) {
	// New user - has api_key
	respNew := RegisterResponse{
		UserID:      "user-123",
		TenantID:    "tenant-456",
		AccessToken: "jwt-token",
		APIKey:      "sk_newkey123",
		IsNewUser:   true,
	}

	dataNew, _ := json.Marshal(respNew)
	if !strings.Contains(string(dataNew), `"api_key":"sk_newkey123"`) {
		t.Error("new user response should contain api_key")
	}

	// Existing user - empty api_key (still present in JSON due to no omitempty)
	respExisting := RegisterResponse{
		UserID:      "user-123",
		TenantID:    "tenant-456",
		AccessToken: "jwt-token",
		APIKey:      "",
		IsNewUser:   false,
	}

	dataExisting, _ := json.Marshal(respExisting)
	if !strings.Contains(string(dataExisting), `"api_key":""`) {
		t.Error("existing user response should contain empty api_key")
	}
	if !strings.Contains(string(dataExisting), `"is_new_user":false`) {
		t.Error("existing user should have is_new_user:false")
	}
}
