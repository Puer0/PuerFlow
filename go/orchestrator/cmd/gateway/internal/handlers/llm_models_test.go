package handlers

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/auth"
	"github.com/google/uuid"
	"go.uber.org/zap"
)

func TestLLMModelsHandler_ListModels(t *testing.T) {
	h := NewLLMModelsHandler("testdata/models.yaml", zap.NewNop())

	req := httptest.NewRequest("GET", "/v1/llm-models", nil)
	ctx := context.WithValue(req.Context(), auth.UserContextKey, &auth.UserContext{
		TenantID: uuid.New(),
	})
	req = req.WithContext(ctx)

	rr := httptest.NewRecorder()
	h.ListLLMModels(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rr.Code, rr.Body.String())
	}

	var resp llmModelsResponse
	if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(resp.Models) == 0 {
		t.Fatal("expected models in response, got none")
	}

	// Verify structure: each model has id, provider, tier
	for _, m := range resp.Models {
		if m.ID == "" {
			t.Error("model has empty id")
		}
		if m.Provider == "" {
			t.Errorf("model %s has empty provider", m.ID)
		}
		if m.Tier == "" {
			t.Errorf("model %s has empty tier", m.ID)
		}
	}

	// Verify we get models from all three tiers
	tiers := map[string]bool{}
	for _, m := range resp.Models {
		tiers[m.Tier] = true
	}
	for _, tier := range []string{"small", "medium", "large"} {
		if !tiers[tier] {
			t.Errorf("expected models from tier %s", tier)
		}
	}
}

func TestLLMModelsHandler_ListModels_SpecificModels(t *testing.T) {
	h := NewLLMModelsHandler("testdata/models.yaml", zap.NewNop())

	req := httptest.NewRequest("GET", "/v1/llm-models", nil)
	ctx := context.WithValue(req.Context(), auth.UserContextKey, &auth.UserContext{
		TenantID: uuid.New(),
	})
	req = req.WithContext(ctx)

	rr := httptest.NewRecorder()
	h.ListLLMModels(rr, req)

	var resp llmModelsResponse
	json.NewDecoder(rr.Body).Decode(&resp)

	// Build lookup
	byID := map[string]llmModelEntry{}
	for _, m := range resp.Models {
		byID[m.ID] = m
	}

	// Check specific models from testdata (tier + priority from model_tiers)
	tests := []struct {
		id       string
		provider string
		tier     string
		priority int
	}{
		{"claude-haiku-4-5-20251001", "anthropic", "small", 1},
		{"claude-sonnet-4-6", "anthropic", "medium", 2},
		{"gpt-5.1", "openai", "large", 1},
	}

	for _, tc := range tests {
		m, ok := byID[tc.id]
		if !ok {
			t.Errorf("model %s not found in response", tc.id)
			continue
		}
		if m.Provider != tc.provider {
			t.Errorf("model %s: expected provider %s, got %s", tc.id, tc.provider, m.Provider)
		}
		if m.Tier != tc.tier {
			t.Errorf("model %s: expected tier %s, got %s", tc.id, tc.tier, m.Tier)
		}
		if m.Priority != tc.priority {
			t.Errorf("model %s: expected priority %d, got %d", tc.id, tc.priority, m.Priority)
		}
	}

	// Catalog-only model (not in model_tiers) should appear with priority 0
	extra, ok := byID["gpt-4.1-2025-04-14"]
	if !ok {
		t.Error("catalog-only model gpt-4.1-2025-04-14 not found")
	} else {
		if extra.Provider != "openai" {
			t.Errorf("gpt-4.1: expected provider openai, got %s", extra.Provider)
		}
		if extra.Tier != "medium" {
			t.Errorf("gpt-4.1: expected tier medium, got %s", extra.Tier)
		}
		if extra.Priority != 0 {
			t.Errorf("gpt-4.1: expected priority 0 (not in model_tiers), got %d", extra.Priority)
		}
	}
}

func TestLLMModelsHandler_ListModels_Unauthorized(t *testing.T) {
	h := NewLLMModelsHandler("testdata/models.yaml", zap.NewNop())

	// No auth context
	req := httptest.NewRequest("GET", "/v1/llm-models", nil)
	rr := httptest.NewRecorder()
	h.ListLLMModels(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}

func TestLLMModelsHandler_ListModels_BadConfig(t *testing.T) {
	h := NewLLMModelsHandler("testdata/nonexistent.yaml", zap.NewNop())

	req := httptest.NewRequest("GET", "/v1/llm-models", nil)
	ctx := context.WithValue(req.Context(), auth.UserContextKey, &auth.UserContext{
		TenantID: uuid.New(),
	})
	req = req.WithContext(ctx)

	rr := httptest.NewRecorder()
	h.ListLLMModels(rr, req)

	if rr.Code != http.StatusInternalServerError {
		t.Errorf("expected 500 for missing config, got %d", rr.Code)
	}
}

func TestLLMModelsHandler_ExcludesUnsupportedProviders(t *testing.T) {
	h := NewLLMModelsHandler("testdata/models.yaml", zap.NewNop())

	req := httptest.NewRequest("GET", "/v1/llm-models", nil)
	ctx := context.WithValue(req.Context(), auth.UserContextKey, &auth.UserContext{
		TenantID: uuid.New(),
	})
	req = req.WithContext(ctx)

	rr := httptest.NewRecorder()
	h.ListLLMModels(rr, req)

	var resp llmModelsResponse
	json.NewDecoder(rr.Body).Decode(&resp)

	for _, m := range resp.Models {
		if m.Provider == "meta" {
			t.Errorf("unsupported provider %s should be filtered out (model: %s)", m.Provider, m.ID)
		}
		if m.ID == "llama-disabled" {
			t.Error("disabled model llama-disabled should be filtered out")
		}
	}
}

func TestLLMModelsHandler_FilterByTier(t *testing.T) {
	h := NewLLMModelsHandler("testdata/models.yaml", zap.NewNop())

	req := httptest.NewRequest("GET", "/v1/llm-models?tier=large", nil)
	ctx := context.WithValue(req.Context(), auth.UserContextKey, &auth.UserContext{
		TenantID: uuid.New(),
	})
	req = req.WithContext(ctx)

	rr := httptest.NewRecorder()
	h.ListLLMModels(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rr.Code)
	}

	var resp llmModelsResponse
	json.NewDecoder(rr.Body).Decode(&resp)

	for _, m := range resp.Models {
		if m.Tier != "large" {
			t.Errorf("expected all models to be tier large, got %s for %s", m.Tier, m.ID)
		}
	}

	if len(resp.Models) == 0 {
		t.Error("expected at least one large tier model")
	}
}
