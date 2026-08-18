package workflows

import (
	"testing"
)

func TestGetSchemaProperties(t *testing.T) {
	tests := []struct {
		name         string
		schema       map[string]interface{}
		expectedKeys []string
	}{
		{
			name:         "nil schema",
			schema:       nil,
			expectedKeys: []string{},
		},
		{
			name:         "empty schema",
			schema:       map[string]interface{}{},
			expectedKeys: []string{},
		},
		{
			name: "schema with properties",
			schema: map[string]interface{}{
				"properties": map[string]interface{}{
					"keywords": map[string]interface{}{"type": "string"},
					"country":  map[string]interface{}{"type": "string"},
					"device":   map[string]interface{}{"type": "string"},
				},
			},
			expectedKeys: []string{"keywords", "country", "device"},
		},
		{
			name: "schema with non-map properties (should handle gracefully)",
			schema: map[string]interface{}{
				"properties": "not a map",
			},
			expectedKeys: []string{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := getSchemaProperties(tt.schema)
			if len(result) != len(tt.expectedKeys) {
				t.Errorf("getSchemaProperties() returned %d fields, expected %d", len(result), len(tt.expectedKeys))
			}
			for _, key := range tt.expectedKeys {
				if _, ok := result[key]; !ok {
					t.Errorf("getSchemaProperties() missing expected key: %s", key)
				}
			}
		})
	}
}

func TestValidateSchemaFieldType(t *testing.T) {
	tests := []struct {
		name       string
		fieldName  string
		value      interface{}
		propSchema map[string]interface{}
		wantErr    bool
	}{
		{
			name:       "valid string",
			fieldName:  "name",
			value:      "test",
			propSchema: map[string]interface{}{"type": "string"},
			wantErr:    false,
		},
		{
			name:       "invalid string (number)",
			fieldName:  "name",
			value:      123,
			propSchema: map[string]interface{}{"type": "string"},
			wantErr:    true,
		},
		{
			name:       "valid integer",
			fieldName:  "count",
			value:      float64(10),
			propSchema: map[string]interface{}{"type": "integer"},
			wantErr:    false,
		},
		{
			name:       "invalid integer (float with decimal)",
			fieldName:  "count",
			value:      10.5,
			propSchema: map[string]interface{}{"type": "integer"},
			wantErr:    true,
		},
		{
			name:       "valid boolean",
			fieldName:  "enabled",
			value:      true,
			propSchema: map[string]interface{}{"type": "boolean"},
			wantErr:    false,
		},
		{
			name:       "invalid boolean (string)",
			fieldName:  "enabled",
			value:      "true",
			propSchema: map[string]interface{}{"type": "boolean"},
			wantErr:    true,
		},
		{
			name:       "valid array",
			fieldName:  "tags",
			value:      []string{"a", "b"},
			propSchema: map[string]interface{}{"type": "array"},
			wantErr:    false,
		},
		{
			name:       "invalid array (string)",
			fieldName:  "tags",
			value:      "not an array",
			propSchema: map[string]interface{}{"type": "array"},
			wantErr:    true,
		},
		{
			name:       "nil value allowed",
			fieldName:  "optional",
			value:      nil,
			propSchema: map[string]interface{}{"type": "string"},
			wantErr:    false,
		},
		{
			name:       "no type in schema allows any",
			fieldName:  "flexible",
			value:      123,
			propSchema: map[string]interface{}{},
			wantErr:    false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateSchemaFieldType(tt.fieldName, tt.value, tt.propSchema)
			if tt.wantErr && err == nil {
				t.Errorf("validateSchemaFieldType() expected error, got nil")
			} else if !tt.wantErr && err != nil {
				t.Errorf("validateSchemaFieldType() unexpected error = %v", err)
			}
		})
	}
}

func TestConvertAgentInputFromTask_NilContext(t *testing.T) {
	input := TaskInput{
		Context: nil,
	}

	_, err := ConvertAgentInputFromTask(input)
	if err == nil {
		t.Error("ConvertAgentInputFromTask() should return error for nil context")
	}
	if err.Error() != "context is required for agent workflow" {
		t.Errorf("ConvertAgentInputFromTask() unexpected error message: %v", err)
	}
}

func TestConvertAgentInputFromTask_MissingAgentID(t *testing.T) {
	tests := []struct {
		name    string
		context map[string]interface{}
	}{
		{
			name:    "empty context",
			context: map[string]interface{}{},
		},
		{
			name: "context without agent key",
			context: map[string]interface{}{
				"other_key": "value",
			},
		},
		{
			name: "context with empty agent",
			context: map[string]interface{}{
				"agent": "",
			},
		},
		{
			name: "context with non-string agent",
			context: map[string]interface{}{
				"agent": 123,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			input := TaskInput{
				Context: tt.context,
			}

			_, err := ConvertAgentInputFromTask(input)
			if err == nil {
				t.Error("ConvertAgentInputFromTask() should return error for missing agent ID")
			}
		})
	}
}

// Note: Full integration tests for ConvertAgentInputFromTask require the agents.yaml config
// to be available. These tests validate the helper functions and error handling.
// For full E2E testing, see the integration test suite.

func TestAgentWorkflowOutputToTaskResult_Success(t *testing.T) {
	output := &AgentWorkflowOutput{
		Success:       true,
		Output:        map[string]interface{}{"keywords": []string{"test", "query"}},
		AgentID:       "keyword-extract",
		ToolName:      "keyword_extract",
		ExecutionTime: 150,
		CostUSD:       0.001,
		TokensUsed:    100,
	}

	result := AgentWorkflowOutputToTaskResult(output)

	if !result.Success {
		t.Error("AgentWorkflowOutputToTaskResult() should return success=true for successful output")
	}
	if result.ErrorMessage != "" {
		t.Errorf("AgentWorkflowOutputToTaskResult() should not have error message, got: %s", result.ErrorMessage)
	}
	if result.Result == "" {
		t.Error("AgentWorkflowOutputToTaskResult() should have result string")
	}
	if result.Metadata == nil {
		t.Error("AgentWorkflowOutputToTaskResult() should have metadata")
	}
	if result.Metadata["agent_id"] != "keyword-extract" {
		t.Errorf("AgentWorkflowOutputToTaskResult() metadata agent_id = %v, want keyword-extract", result.Metadata["agent_id"])
	}
}

func TestAgentWorkflowOutputToTaskResult_Failure(t *testing.T) {
	output := &AgentWorkflowOutput{
		Success: false,
		Error:   "tool execution failed",
		AgentID: "keyword-extract",
	}

	result := AgentWorkflowOutputToTaskResult(output)

	if result.Success {
		t.Error("AgentWorkflowOutputToTaskResult() should return success=false for failed output")
	}
	if result.ErrorMessage != "tool execution failed" {
		t.Errorf("AgentWorkflowOutputToTaskResult() error message = %s, want 'tool execution failed'", result.ErrorMessage)
	}
}
