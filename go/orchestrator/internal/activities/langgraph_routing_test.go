package activities

import "testing"

func TestAttachLangGraphModelRoutingDefaultsByMode(t *testing.T) {
	simple := map[string]interface{}{}
	attachLangGraphModelRouting("simple", simple)
	if simple["model_tier"] != "small" {
		t.Fatalf("simple default tier = %v", simple["model_tier"])
	}
	if simple["synthesis_model_tier"] != "large" || simple["utility_model_tier"] != "small" {
		t.Fatalf("stage tiers = %#v", simple)
	}

	dag := map[string]interface{}{}
	attachLangGraphModelRouting("dag", dag)
	if dag["model_tier"] != "medium" {
		t.Fatalf("dag default tier = %v", dag["model_tier"])
	}

	kept := map[string]interface{}{"model_tier": "large", "provider_override": "openai"}
	attachLangGraphModelRouting("research", kept)
	if kept["model_tier"] != "large" {
		t.Fatalf("explicit model_tier overwritten: %v", kept["model_tier"])
	}
	if kept["provider_override"] != "openai" {
		t.Fatalf("provider_override dropped: %#v", kept)
	}
}
