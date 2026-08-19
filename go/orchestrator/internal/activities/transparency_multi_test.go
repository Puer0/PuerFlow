package activities

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestDeterminePlatforms(t *testing.T) {
	tests := []struct {
		name       string
		country    string
		platforms  []string
		wantGoogle bool
		wantYahoo  bool
		wantMeta   bool
	}{
		{
			name:       "jp country enables all platforms",
			country:    "jp",
			wantGoogle: true,
			wantYahoo:  true,
			wantMeta:   true,
		},
		{
			name:       "JP uppercase also works",
			country:    "JP",
			wantGoogle: true,
			wantYahoo:  true,
			wantMeta:   true,
		},
		{
			name:       "us country enables google and meta only",
			country:    "us",
			wantGoogle: true,
			wantYahoo:  false,
			wantMeta:   true,
		},
		{
			name:       "empty country enables google and meta",
			country:    "",
			wantGoogle: true,
			wantYahoo:  false,
			wantMeta:   true,
		},
		{
			name:       "explicit platforms override: google only",
			country:    "jp",
			platforms:  []string{"google"},
			wantGoogle: true,
			wantYahoo:  false,
			wantMeta:   false,
		},
		{
			name:       "explicit platforms override: yahoo only",
			country:    "us",
			platforms:  []string{"yahoo"},
			wantGoogle: false,
			wantYahoo:  true,
			wantMeta:   false,
		},
		{
			name:       "explicit platforms override: all three",
			country:    "us",
			platforms:  []string{"google", "yahoo", "meta"},
			wantGoogle: true,
			wantYahoo:  true,
			wantMeta:   true,
		},
		{
			name:       "invalid platform names select nothing",
			country:    "us",
			platforms:  []string{"tiktok", "linkedin"},
			wantGoogle: false,
			wantYahoo:  false,
			wantMeta:   false,
		},
		{
			name:       "mixed valid and invalid platforms",
			country:    "us",
			platforms:  []string{"google", "tiktok"},
			wantGoogle: true,
			wantYahoo:  false,
			wantMeta:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			google, yahoo, meta := determinePlatforms(tt.country, tt.platforms)
			assert.Equal(t, tt.wantGoogle, google, "google")
			assert.Equal(t, tt.wantYahoo, yahoo, "yahoo")
			assert.Equal(t, tt.wantMeta, meta, "meta")
		})
	}
}

func TestExtractCostFromResult(t *testing.T) {
	tests := []struct {
		name     string
		result   *ToolExecuteResponse
		wantCost float64
	}{
		{
			name:     "cost from metadata api_cost_usd",
			result:   &ToolExecuteResponse{Metadata: map[string]interface{}{"api_cost_usd": 0.015}},
			wantCost: 0.015,
		},
		{
			name:     "cost from metadata cost_usd",
			result:   &ToolExecuteResponse{Metadata: map[string]interface{}{"cost_usd": 0.004}},
			wantCost: 0.004,
		},
		{
			name:     "cost from output body cost_usd",
			result:   &ToolExecuteResponse{Output: map[string]interface{}{"cost_usd": 0.01, "data": "stuff"}},
			wantCost: 0.01,
		},
		{
			name:     "metadata takes precedence over output",
			result:   &ToolExecuteResponse{Metadata: map[string]interface{}{"api_cost_usd": 0.02}, Output: map[string]interface{}{"cost_usd": 0.01}},
			wantCost: 0.02,
		},
		{
			name:     "no cost anywhere returns zero",
			result:   &ToolExecuteResponse{Output: map[string]interface{}{"data": "stuff"}},
			wantCost: 0,
		},
		{
			name:     "nil metadata and non-map output returns zero",
			result:   &ToolExecuteResponse{Output: "just a string"},
			wantCost: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cost := extractCostFromResult(tt.result)
			assert.InDelta(t, tt.wantCost, cost, 0.0001)
		})
	}
}
