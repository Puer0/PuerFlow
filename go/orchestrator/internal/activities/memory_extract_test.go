package activities

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"go.temporal.io/sdk/testsuite"
)

func TestValidUserID(t *testing.T) {
	t.Run("accepts valid ids", func(t *testing.T) {
		valid := []string{
			"user-123",
			"USER_123",
			"a",
			"abc_DEF-123",
		}

		for _, id := range valid {
			if err := validUserID(id); err != nil {
				t.Fatalf("expected %q to be valid, got %v", id, err)
			}
		}
	})

	t.Run("rejects invalid ids", func(t *testing.T) {
		invalid := []string{
			"../escape",
			"user;rm",
			"user/123",
			"用户",
			"",
			".hidden",
			".",
			"..",
			"user..id",
			"user@id",
		}

		for _, id := range invalid {
			if err := validUserID(id); err == nil {
				t.Fatalf("expected %q to be invalid", id)
			}
		}
	})
}

func TestParseMemoryIndex(t *testing.T) {
	t.Run("empty content", func(t *testing.T) {
		header, entries := parseMemoryIndex("# User Memory\n\n")
		if !strings.Contains(header, "User Memory") {
			t.Fatal("expected header to contain 'User Memory'")
		}
		if len(entries) != 0 {
			t.Fatalf("expected 0 entries, got %d", len(entries))
		}
	})

	t.Run("entries with timestamps", func(t *testing.T) {
		content := "# User Memory\n\n## foo.md\n<!-- updated:2025-01-01T00:00:00Z -->\nSummary of foo\n\n## bar.md\n<!-- updated:2025-06-15T12:00:00Z -->\nSummary of bar\n"
		_, entries := parseMemoryIndex(content)
		if len(entries) != 2 {
			t.Fatalf("expected 2 entries, got %d", len(entries))
		}
		if entries[0].Path != "foo.md" {
			t.Fatalf("expected foo.md, got %s", entries[0].Path)
		}
		if entries[0].Summary != "Summary of foo" {
			t.Fatalf("expected 'Summary of foo', got %q", entries[0].Summary)
		}
		if entries[0].UpdatedAt.Year() != 2025 {
			t.Fatalf("expected 2025 year, got %d", entries[0].UpdatedAt.Year())
		}
		if entries[1].Path != "bar.md" {
			t.Fatalf("expected bar.md, got %s", entries[1].Path)
		}
	})

	t.Run("entries without timestamps (legacy)", func(t *testing.T) {
		content := "# User Memory\n\n## old.md\nLegacy summary\n"
		_, entries := parseMemoryIndex(content)
		if len(entries) != 1 {
			t.Fatalf("expected 1 entry, got %d", len(entries))
		}
		if !entries[0].UpdatedAt.IsZero() {
			t.Fatal("expected zero time for legacy entry")
		}
		if entries[0].Summary != "Legacy summary" {
			t.Fatalf("expected 'Legacy summary', got %q", entries[0].Summary)
		}
	})
}

func TestRenderMemoryIndex(t *testing.T) {
	entries := []memoryEntry{
		{Path: "foo.md", Summary: "Foo summary", UpdatedAt: time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)},
		{Path: "bar.md", Summary: "Bar summary", UpdatedAt: time.Date(2025, 6, 15, 12, 0, 0, 0, time.UTC)},
	}
	result := renderMemoryIndex("# User Memory\n", entries)

	if !strings.Contains(result, "## foo.md") {
		t.Fatal("expected foo.md heading")
	}
	if !strings.Contains(result, "<!-- updated:2025-01-01T00:00:00Z -->") {
		t.Fatal("expected timestamp comment for foo")
	}
	if !strings.Contains(result, "Foo summary") {
		t.Fatal("expected foo summary")
	}
	if !strings.Contains(result, "## bar.md") {
		t.Fatal("expected bar.md heading")
	}
}

func TestRoundTripParseRender(t *testing.T) {
	t.Run("single-line summaries", func(t *testing.T) {
		entries := []memoryEntry{
			{Path: "a.md", Summary: "Summary A", UpdatedAt: time.Date(2025, 3, 1, 0, 0, 0, 0, time.UTC)},
			{Path: "b.md", Summary: "Summary B", UpdatedAt: time.Date(2025, 4, 1, 0, 0, 0, 0, time.UTC)},
		}
		rendered := renderMemoryIndex("# User Memory\n", entries)
		_, parsed := parseMemoryIndex(rendered)

		if len(parsed) != 2 {
			t.Fatalf("expected 2 entries after round-trip, got %d", len(parsed))
		}
		if parsed[0].Path != "a.md" || parsed[0].Summary != "Summary A" {
			t.Fatalf("entry 0 mismatch: %+v", parsed[0])
		}
		if parsed[1].Path != "b.md" || parsed[1].Summary != "Summary B" {
			t.Fatalf("entry 1 mismatch: %+v", parsed[1])
		}
		if !parsed[0].UpdatedAt.Equal(entries[0].UpdatedAt) {
			t.Fatalf("timestamp 0 mismatch: got %v, want %v", parsed[0].UpdatedAt, entries[0].UpdatedAt)
		}
	})

	t.Run("zero-timestamp entries no duplication", func(t *testing.T) {
		// Entries with zero UpdatedAt should not accumulate <!-- updated:0001-01-01T00:00:00Z --> lines
		entries := []memoryEntry{
			{Path: "old.md", Summary: "Legacy entry"},
			{Path: "new.md", Summary: "Recent entry", UpdatedAt: time.Date(2025, 3, 1, 0, 0, 0, 0, time.UTC)},
		}
		// Simulate multiple render→parse cycles
		rendered := renderMemoryIndex("# User Memory\n", entries)
		for i := 0; i < 5; i++ {
			_, parsed := parseMemoryIndex(rendered)
			rendered = renderMemoryIndex("# User Memory\n", parsed)
		}
		_, final := parseMemoryIndex(rendered)
		if len(final) != 2 {
			t.Fatalf("expected 2 entries after 5 cycles, got %d", len(final))
		}
		if final[0].Summary != "Legacy entry" {
			t.Fatalf("zero-timestamp summary corrupted: %q", final[0].Summary)
		}
		if strings.Contains(final[0].Summary, "<!-- updated:") {
			t.Fatal("timestamp comment leaked into summary for zero-time entry")
		}
		if !final[0].UpdatedAt.IsZero() {
			t.Fatalf("expected zero time preserved, got %v", final[0].UpdatedAt)
		}
		count := strings.Count(rendered, "<!-- updated:")
		if count != 1 {
			t.Fatalf("expected exactly 1 timestamp comment (for new.md), got %d", count)
		}
	})

	t.Run("multi-line bullet summaries", func(t *testing.T) {
		multiLine := "- EC2 t3.medium costs $0.0416/hr in ap-northeast-1\n- Reserved instances save 40% for 1-year commitment\n- Spot instances available at 70% discount but can be interrupted"
		entries := []memoryEntry{
			{Path: "aws-pricing.md", Summary: multiLine, UpdatedAt: time.Date(2025, 5, 1, 0, 0, 0, 0, time.UTC)},
			{Path: "redis.md", Summary: "- Use SCAN not KEYS in production\n- COUNT is a hint, not a limit", UpdatedAt: time.Date(2025, 6, 1, 0, 0, 0, 0, time.UTC)},
		}
		rendered := renderMemoryIndex("# User Memory\n", entries)
		_, parsed := parseMemoryIndex(rendered)

		if len(parsed) != 2 {
			t.Fatalf("expected 2 entries, got %d", len(parsed))
		}
		if parsed[0].Summary != multiLine {
			t.Fatalf("multi-line summary not preserved:\ngot:  %q\nwant: %q", parsed[0].Summary, multiLine)
		}
		if parsed[1].Path != "redis.md" {
			t.Fatalf("second entry path mismatch: %s", parsed[1].Path)
		}
	})
}

func TestUpdateMemoryIndex(t *testing.T) {
	t.Run("creates new index", func(t *testing.T) {
		dir := t.TempDir()
		err := updateMemoryIndex(dir, "notes.md", "Some notes")
		if err != nil {
			t.Fatal(err)
		}

		data, _ := os.ReadFile(filepath.Join(dir, "MEMORY.md"))
		content := string(data)
		if !strings.Contains(content, "## notes.md") {
			t.Fatal("expected notes.md heading")
		}
		if !strings.Contains(content, "Some notes") {
			t.Fatal("expected summary")
		}
		if !strings.Contains(content, "<!-- updated:") {
			t.Fatal("expected timestamp comment")
		}
	})

	t.Run("deduplicates by path", func(t *testing.T) {
		dir := t.TempDir()
		_ = updateMemoryIndex(dir, "topic.md", "First version")
		_ = updateMemoryIndex(dir, "topic.md", "Updated version")

		data, _ := os.ReadFile(filepath.Join(dir, "MEMORY.md"))
		content := string(data)
		if strings.Count(content, "## topic.md") != 1 {
			t.Fatal("expected exactly one heading for topic.md")
		}
		if !strings.Contains(content, "Updated version") {
			t.Fatal("expected updated summary")
		}
		if strings.Contains(content, "First version") {
			t.Fatal("old summary should be replaced")
		}
	})

	t.Run("evicts oldest when over cap", func(t *testing.T) {
		dir := t.TempDir()

		total := maxMemoryIndexEntries + 5
		for i := 0; i < total; i++ {
			name := fmt.Sprintf("entry-%03d.md", i)
			err := updateMemoryIndex(dir, name, "Summary for "+name)
			if err != nil {
				t.Fatalf("entry %d: %v", i, err)
			}
		}

		data, _ := os.ReadFile(filepath.Join(dir, "MEMORY.md"))
		content := string(data)

		headingCount := strings.Count(content, "\n## ")
		if headingCount > maxMemoryIndexEntries {
			t.Fatalf("expected at most %d entries, got %d", maxMemoryIndexEntries, headingCount)
		}

		// Oldest entries (000-004) should be evicted
		if strings.Contains(content, "entry-000.md") {
			t.Fatal("oldest entry should have been evicted")
		}
		// Newest entry should remain
		last := fmt.Sprintf("entry-%03d.md", total-1)
		if !strings.Contains(content, last) {
			t.Fatalf("newest entry %s should be present", last)
		}
	})

	t.Run("updating existing entry does not trigger eviction", func(t *testing.T) {
		dir := t.TempDir()

		// Fill to exactly the cap
		for i := 0; i < maxMemoryIndexEntries; i++ {
			name := "file-" + fmt.Sprintf("%d", i) + ".md"
			_ = updateMemoryIndex(dir, name, "Summary "+fmt.Sprintf("%d", i))
		}

		// Update the first entry — should not evict anything
		_ = updateMemoryIndex(dir, "file-0.md", "Updated summary")

		data, _ := os.ReadFile(filepath.Join(dir, "MEMORY.md"))
		content := string(data)
		headingCount := strings.Count(content, "\n## ")
		if headingCount != maxMemoryIndexEntries {
			t.Fatalf("expected exactly %d entries, got %d", maxMemoryIndexEntries, headingCount)
		}
		if !strings.Contains(content, "Updated summary") {
			t.Fatal("expected updated summary")
		}
	})

	t.Run("handles legacy entries without timestamps", func(t *testing.T) {
		dir := t.TempDir()
		// Write a legacy-format MEMORY.md (no timestamps)
		legacy := "# User Memory\n\n## old-note.md\nOld note without timestamp\n\n## another.md\nAnother old note\n"
		os.WriteFile(filepath.Join(dir, "MEMORY.md"), []byte(legacy), 0644)

		// Add a new entry — should not crash, legacy entries get zero time
		err := updateMemoryIndex(dir, "new.md", "New entry")
		if err != nil {
			t.Fatal(err)
		}

		data, _ := os.ReadFile(filepath.Join(dir, "MEMORY.md"))
		content := string(data)
		if !strings.Contains(content, "## new.md") {
			t.Fatal("expected new entry")
		}
		// Legacy entries should still be present (under cap)
		if !strings.Contains(content, "## old-note.md") {
			t.Fatal("legacy entry should be preserved")
		}
	})

	t.Run("legacy entries evicted first", func(t *testing.T) {
		dir := t.TempDir()

		// Seed with a legacy entry (no timestamp → zero time → oldest)
		legacy := "# User Memory\n\n## legacy.md\nLegacy entry\n"
		os.WriteFile(filepath.Join(dir, "MEMORY.md"), []byte(legacy), 0644)

		// Fill to cap with timestamped entries
		for i := 0; i < maxMemoryIndexEntries; i++ {
			name := "ts-" + fmt.Sprintf("%d", i) + ".md"
			_ = updateMemoryIndex(dir, name, "Timestamped "+fmt.Sprintf("%d", i))
		}

		data, _ := os.ReadFile(filepath.Join(dir, "MEMORY.md"))
		content := string(data)

		// Legacy entry (zero time) should be evicted first
		if strings.Contains(content, "## legacy.md") {
			t.Fatal("legacy entry should have been evicted (oldest due to zero time)")
		}
	})
}

func TestMemoryExtractActivityWritesTriples(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestActivityEnvironment()
	env.RegisterActivity(ExtractMemoryActivity)

	memRoot := t.TempDir()
	userID := "user-triples"
	query := strings.Repeat("q", 520)
	result := strings.Repeat("result ", 120)

	var calls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/json")

		var payload []byte
		var err error
		switch calls {
		case 1:
			payload, err = json.Marshal(map[string]interface{}{
				"worth_remembering": true,
				"title":             "Rust memory preferences",
				"summary":           "- Prefers Rust for systems work.\n- Uses Redis for caching.",
				"content":           "The user prefers Rust for systems programming and prefers Redis caching. This preference is consistent across repeated architecture decisions and is intended to be reused as a memory.",
				"suggested_path":    "team-preferences.md",
				"tags":              []string{"prefs", "tech"},
				"triples": []map[string]string{
					{"h": "wayland", "r": "prefers", "t": "rust_for_systems_programming"},
					{"h": "redis", "r": "better_than_for", "t": "memcached_when_persistence_needed"},
					{"h": "", "r": "invalid", "t": "ignored"},
				},
			})
		case 2:
			payload, err = json.Marshal(map[string]interface{}{
				"worth_remembering": true,
				"title":             "Docker guidance",
				"summary":           "- Running containers as non-root user is required in production.",
				"content":           "Production containers should run as non-root users with hardened runtime settings. Enforce non-root operation to reduce exploit impact in long-running services.",
				"suggested_path":    "team-preferences.md",
				"tags":              []string{"security"},
				"triples": []map[string]string{
					{"h": "wayland", "r": "prefers", "t": "rust_for_systems_programming"},
					{"h": "docker_production", "r": "requires", "t": "non_root_user"},
				},
			})
		default:
			payload = []byte(`{"worth_remembering":false}`)
			err = nil
		}
		if err != nil {
			t.Fatalf("failed to marshal response: %v", err)
		}
		_, _ = w.Write(payload)
	}))
	defer server.Close()

	t.Setenv("USER_MEMORY_ENABLED", "1")
	t.Setenv("LLM_SERVICE_URL", server.URL)
	t.Setenv("SHANNON_USER_MEMORY_DIR", memRoot)

	input := MemoryExtractInput{
		UserID:           userID,
		TenantID:         "tenant-1",
		SessionID:        "session-1",
		Query:            query,
		Result:           result,
		ParentWorkflowID: "workflow-1",
	}

	// First extraction
	val, err := env.ExecuteActivity(ExtractMemoryActivity, input)
	if err != nil {
		t.Fatalf("first extract failed: %v", err)
	}
	var first MemoryExtractResult
	if err := val.Get(&first); err != nil {
		t.Fatalf("first extract decode: %v", err)
	}
	if !first.Extracted {
		t.Fatalf("expected first extraction to be stored, skip_reason=%s", first.SkipReason)
	}

	userMemDir := filepath.Join(memRoot, userID, "memory")
	mdPath := filepath.Join(userMemDir, "team-preferences.md")
	triplesPath := filepath.Join(userMemDir, "triples.jsonl")

	mdData, err := os.ReadFile(mdPath)
	if err != nil {
		t.Fatalf("failed to read memory file: %v", err)
	}
	if !strings.Contains(string(mdData), "# Rust memory preferences") {
		t.Fatal("expected memory file title")
	}

	triples := readMemoryTriplesForTest(t, triplesPath)
	if len(triples) != 2 {
		t.Fatalf("expected 2 valid triples after first extraction, got %d", len(triples))
	}
	for _, tr := range triples {
		if tr.H == "" || tr.R == "" || tr.T == "" || tr.Src == "" || tr.Ts == "" {
			t.Fatalf("invalid triple record: %+v", tr)
		}
		if _, parseErr := time.Parse(time.RFC3339, tr.Ts); parseErr != nil {
			t.Fatalf("invalid timestamp: %s", tr.Ts)
		}
	}

	// Second extraction (same file path — tests dedup + append)
	val2, err := env.ExecuteActivity(ExtractMemoryActivity, input)
	if err != nil {
		t.Fatalf("second extract failed: %v", err)
	}
	var second MemoryExtractResult
	if err := val2.Get(&second); err != nil {
		t.Fatalf("second extract decode: %v", err)
	}
	if !second.Extracted {
		t.Fatalf("expected second extraction to be stored, skip_reason=%s", second.SkipReason)
	}

	indexData, err := os.ReadFile(filepath.Join(userMemDir, "MEMORY.md"))
	if err != nil {
		t.Fatalf("failed to read memory index: %v", err)
	}
	if strings.Count(string(indexData), "## team-preferences.md") != 1 {
		t.Fatalf("expected deduplicated memory index entry, got:\n%s", string(indexData))
	}

	if !strings.Contains(string(indexData), "non-root user") {
		t.Fatalf("expected updated summary to appear in MEMORY.md: %s", string(indexData))
	}

	allTriples := readMemoryTriplesForTest(t, triplesPath)
	if len(allTriples) != 4 {
		t.Fatalf("expected appended triples across calls, got %d", len(allTriples))
	}

	srcs := make([]string, 0, len(allTriples))
	for _, tr := range allTriples {
		if tr.Src != "team-preferences.md" {
			t.Fatalf("expected src to match file path, got %q", tr.Src)
		}
		srcs = append(srcs, tr.H+":"+tr.R+":"+tr.T)
	}
	if !slices.Contains(srcs, "wayland:prefers:rust_for_systems_programming") {
		t.Fatalf("expected repeated triple to be preserved in append log: %#v", srcs)
	}
	if !slices.Contains(srcs, "docker_production:requires:non_root_user") {
		t.Fatalf("expected second triple in append log: %#v", srcs)
	}
}

func readMemoryTriplesForTest(t *testing.T, path string) []memoryTripleRecord {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("failed to read triples file: %v", err)
	}

	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	if len(lines) == 1 && strings.TrimSpace(lines[0]) == "" {
		return nil
	}

	records := make([]memoryTripleRecord, 0, len(lines))
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var rec memoryTripleRecord
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			t.Fatalf("invalid triple JSONL line %q: %v", line, err)
		}
		records = append(records, rec)
	}
	return records
}
