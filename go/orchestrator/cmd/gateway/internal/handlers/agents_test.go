package handlers

import (
	"testing"

	"github.com/Kocoro-lab/Shannon/go/orchestrator/internal/activities"
)

func TestValidateAgentInput_RequiredFields(t *testing.T) {
	agent := &activities.AgentDefinition{
		Name: "test-agent",
		InputSchema: map[string]interface{}{
			"required": []interface{}{"keywords", "country"},
			"properties": map[string]interface{}{
				"keywords": map[string]interface{}{
					"type": "string",
				},
				"country": map[string]interface{}{
					"type": "string",
				},
			},
		},
	}

	tests := []struct {
		name    string
		input   map[string]interface{}
		wantErr bool
		errMsg  string
	}{
		{
			name: "all required fields present",
			input: map[string]interface{}{
				"keywords": "test query",
				"country":  "us",
			},
			wantErr: false,
		},
		{
			name: "missing required field keywords",
			input: map[string]interface{}{
				"country": "us",
			},
			wantErr: true,
			errMsg:  "missing required field: keywords",
		},
		{
			name: "missing required field country",
			input: map[string]interface{}{
				"keywords": "test",
			},
			wantErr: true,
			errMsg:  "missing required field: country",
		},
		{
			name:    "missing all required fields",
			input:   map[string]interface{}{},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateAgentInput(agent, tt.input)
			if tt.wantErr {
				if err == nil {
					t.Errorf("ValidateAgentInput() expected error, got nil")
					return
				}
				if tt.errMsg != "" && err.Error() != "input validation failed: "+tt.errMsg {
					// Check if error contains expected message
					if !contains(err.Error(), tt.errMsg) {
						t.Errorf("ValidateAgentInput() error = %v, want to contain %v", err, tt.errMsg)
					}
				}
			} else if err != nil {
				t.Errorf("ValidateAgentInput() unexpected error = %v", err)
			}
		})
	}
}

func TestValidateAgentInput_TypeValidation(t *testing.T) {
	agent := &activities.AgentDefinition{
		Name: "test-agent",
		InputSchema: map[string]interface{}{
			"properties": map[string]interface{}{
				"name": map[string]interface{}{
					"type": "string",
				},
				"count": map[string]interface{}{
					"type": "integer",
				},
				"enabled": map[string]interface{}{
					"type": "boolean",
				},
				"tags": map[string]interface{}{
					"type": "array",
				},
				"config": map[string]interface{}{
					"type": "object",
				},
			},
		},
	}

	tests := []struct {
		name    string
		input   map[string]interface{}
		wantErr bool
	}{
		{
			name:    "valid string",
			input:   map[string]interface{}{"name": "test"},
			wantErr: false,
		},
		{
			name:    "invalid string (number)",
			input:   map[string]interface{}{"name": 123},
			wantErr: true,
		},
		{
			name:    "valid integer",
			input:   map[string]interface{}{"count": 10},
			wantErr: false,
		},
		{
			name:    "valid integer from float64",
			input:   map[string]interface{}{"count": float64(10)},
			wantErr: false,
		},
		{
			name:    "invalid integer (float with decimal)",
			input:   map[string]interface{}{"count": 10.5},
			wantErr: true,
		},
		{
			name:    "valid boolean",
			input:   map[string]interface{}{"enabled": true},
			wantErr: false,
		},
		{
			name:    "invalid boolean (string)",
			input:   map[string]interface{}{"enabled": "true"},
			wantErr: true,
		},
		{
			name:    "valid array",
			input:   map[string]interface{}{"tags": []string{"a", "b"}},
			wantErr: false,
		},
		{
			name:    "invalid array (string)",
			input:   map[string]interface{}{"tags": "not an array"},
			wantErr: true,
		},
		{
			name:    "valid object",
			input:   map[string]interface{}{"config": map[string]interface{}{"key": "value"}},
			wantErr: false,
		},
		{
			name:    "invalid object (string)",
			input:   map[string]interface{}{"config": "not an object"},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateAgentInput(agent, tt.input)
			if tt.wantErr && err == nil {
				t.Errorf("ValidateAgentInput() expected error, got nil")
			} else if !tt.wantErr && err != nil {
				t.Errorf("ValidateAgentInput() unexpected error = %v", err)
			}
		})
	}
}

func TestValidateAgentInput_UnknownFields(t *testing.T) {
	agent := &activities.AgentDefinition{
		Name: "test-agent",
		InputSchema: map[string]interface{}{
			"properties": map[string]interface{}{
				"allowed_field": map[string]interface{}{
					"type": "string",
				},
			},
		},
	}

	tests := []struct {
		name    string
		input   map[string]interface{}
		wantErr bool
	}{
		{
			name:    "only allowed field",
			input:   map[string]interface{}{"allowed_field": "test"},
			wantErr: false,
		},
		{
			name:    "unknown field rejected",
			input:   map[string]interface{}{"unknown_field": "hacker input"},
			wantErr: true,
		},
		{
			name: "mixed allowed and unknown fields",
			input: map[string]interface{}{
				"allowed_field": "test",
				"malicious":     "injection attempt",
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateAgentInput(agent, tt.input)
			if tt.wantErr && err == nil {
				t.Errorf("ValidateAgentInput() expected error for unknown field, got nil")
			} else if !tt.wantErr && err != nil {
				t.Errorf("ValidateAgentInput() unexpected error = %v", err)
			}
		})
	}
}

func TestValidateAgentInput_EnumValidation(t *testing.T) {
	agent := &activities.AgentDefinition{
		Name: "test-agent",
		InputSchema: map[string]interface{}{
			"properties": map[string]interface{}{
				"device": map[string]interface{}{
					"type": "string",
					"enum": []interface{}{"desktop", "mobile", "tablet"},
				},
			},
		},
	}

	tests := []struct {
		name    string
		input   map[string]interface{}
		wantErr bool
	}{
		{
			name:    "valid enum value",
			input:   map[string]interface{}{"device": "desktop"},
			wantErr: false,
		},
		{
			name:    "another valid enum value",
			input:   map[string]interface{}{"device": "mobile"},
			wantErr: false,
		},
		{
			name:    "invalid enum value",
			input:   map[string]interface{}{"device": "smartphone"},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateAgentInput(agent, tt.input)
			if tt.wantErr && err == nil {
				t.Errorf("ValidateAgentInput() expected error for invalid enum, got nil")
			} else if !tt.wantErr && err != nil {
				t.Errorf("ValidateAgentInput() unexpected error = %v", err)
			}
		})
	}
}

func TestValidateAgentInput_NilSchema(t *testing.T) {
	agent := &activities.AgentDefinition{
		Name:        "test-agent",
		InputSchema: nil,
	}

	// Should allow any input when no schema is defined
	err := ValidateAgentInput(agent, map[string]interface{}{
		"any_field": "any_value",
	})
	if err != nil {
		t.Errorf("ValidateAgentInput() with nil schema should allow any input, got error = %v", err)
	}
}

// Helper function to check if string contains substring
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
