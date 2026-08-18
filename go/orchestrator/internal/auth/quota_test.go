package auth

import (
	"testing"
)

func TestDefaultQuotaDefaults(t *testing.T) {
	quotas := defaultQuotaDefaults()

	// Verify built-in OSS defaults.
	free, ok := quotas["free"]
	if !ok {
		t.Fatal("Expected 'free' tier in quota defaults")
	}

	if free.MonthlyTokens != 1_000_000 {
		t.Errorf("Free monthly_tokens: got %d, want 1000000", free.MonthlyTokens)
	}
	if free.DailyTokens != 500_000 {
		t.Errorf("Free daily_tokens: got %d, want 500000", free.DailyTokens)
	}
	if free.OverageEnabled != false {
		t.Errorf("Free overage_enabled: got %v, want false", free.OverageEnabled)
	}
	if free.HardCapMonthlyTokens != 1_000_000 {
		t.Errorf("Free hard_cap: got %d, want 1000000", free.HardCapMonthlyTokens)
	}

	// Verify pro tier
	pro, ok := quotas["pro"]
	if !ok {
		t.Fatal("Expected 'pro' tier in quota defaults")
	}

	if pro.MonthlyTokens != 10_000_000 {
		t.Errorf("Pro monthly_tokens: got %d, want 10000000", pro.MonthlyTokens)
	}
	if pro.DailyTokens != 3_000_000 {
		t.Errorf("Pro daily_tokens: got %d, want 3000000", pro.DailyTokens)
	}
	if pro.OverageEnabled != true {
		t.Errorf("Pro overage_enabled: got %v, want true", pro.OverageEnabled)
	}
	if pro.OveragePer1MTokens != 10.00 {
		t.Errorf("Pro overage_per_1m_tokens: got %f, want 10.00", pro.OveragePer1MTokens)
	}
	if pro.HardCapMonthlyTokens != 100_000_000 {
		t.Errorf("Pro hard_cap: got %d, want 100000000", pro.HardCapMonthlyTokens)
	}
	if pro.OverageGraceTokens != 1_000_000 {
		t.Errorf("Pro overage_grace_tokens: got %d, want 1000000", pro.OverageGraceTokens)
	}

	// Verify max tier
	max, ok := quotas["max"]
	if !ok {
		t.Fatal("Expected 'max' tier in quota defaults")
	}

	if max.MonthlyTokens != 50_000_000 {
		t.Errorf("Max monthly_tokens: got %d, want 50000000", max.MonthlyTokens)
	}
	if max.OveragePer1MTokens != 8.00 {
		t.Errorf("Max overage_per_1m_tokens: got %f, want 8.00", max.OveragePer1MTokens)
	}

	// Verify enterprise tier
	enterprise, ok := quotas["enterprise"]
	if !ok {
		t.Fatal("Expected 'enterprise' tier in quota defaults")
	}

	if enterprise.MonthlyTokens != 200_000_000 {
		t.Errorf("Enterprise monthly_tokens: got %d, want 200000000", enterprise.MonthlyTokens)
	}
	if enterprise.DailyTokens != 50_000_000 {
		t.Errorf("Enterprise daily_tokens: got %d, want 50000000", enterprise.DailyTokens)
	}
	if enterprise.OveragePer1MTokens != 6.00 {
		t.Errorf("Enterprise overage_per_1m_tokens: got %f, want 6.00", enterprise.OveragePer1MTokens)
	}
}

func TestGetQuotaDefaultsReturnsCopy(t *testing.T) {
	service := &Service{
		quotaDefaults: defaultQuotaDefaults(),
	}

	first := service.GetQuotaDefaults()
	first["free"] = QuotaDefaults{MonthlyTokens: 123}

	second := service.GetQuotaDefaults()
	if second["free"].MonthlyTokens != 1_000_000 {
		t.Fatalf("expected built-in defaults to remain unchanged, got %d", second["free"].MonthlyTokens)
	}
}
