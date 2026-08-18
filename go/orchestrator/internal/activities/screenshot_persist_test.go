package activities

import (
	"encoding/base64"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"go.uber.org/zap"
)

func TestPersistScreenshot(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	// Create temp dir for session workspaces
	tmpDir := t.TempDir()
	t.Setenv("SHANNON_SESSION_WORKSPACES_DIR", tmpDir)

	// Create a fake PNG (1KB is enough for all tests)
	fakeImage := make([]byte, 1024)
	for i := range fakeImage {
		fakeImage[i] = byte(i % 256)
	}
	b64Data := base64.StdEncoding.EncodeToString(fakeImage)

	t.Run("basic persist", func(t *testing.T) {
		relPath := persistScreenshot(logger, "test-session-123", "wf-abcdef12", 0, b64Data)
		if relPath == "" {
			t.Fatal("expected non-empty relPath")
		}
		if !strings.HasPrefix(relPath, "screenshots/") {
			t.Errorf("expected relPath to start with 'screenshots/', got %s", relPath)
		}
		if !strings.HasSuffix(relPath, "_0.png") {
			t.Errorf("expected relPath to end with '_0.png', got %s", relPath)
		}

		// Verify file exists and has correct content
		absPath := filepath.Join(tmpDir, "test-session-123", relPath)
		data, err := os.ReadFile(absPath)
		if err != nil {
			t.Fatalf("failed to read persisted file: %v", err)
		}
		if len(data) != len(fakeImage) {
			t.Errorf("expected %d bytes, got %d", len(fakeImage), len(data))
		}
	})

	t.Run("with data URI prefix", func(t *testing.T) {
		dataURI := "data:image/png;base64," + b64Data
		relPath := persistScreenshot(logger, "test-session-456", "wf-xyz", 1, dataURI)
		if relPath == "" {
			t.Fatal("expected non-empty relPath for data URI input")
		}
		if !strings.Contains(relPath, "_1.png") {
			t.Errorf("expected index 1 in filename, got %s", relPath)
		}
	})

	t.Run("too short data is skipped", func(t *testing.T) {
		relPath := persistScreenshot(logger, "test-session-789", "wf-short", 0, "abc")
		if relPath != "" {
			t.Errorf("expected empty relPath for short data, got %s", relPath)
		}
	})

	t.Run("exactly at minimum length succeeds", func(t *testing.T) {
		// 100 bytes base64-encoded is 136 chars — above the 100-char guard
		smallImage := make([]byte, 100)
		for i := range smallImage {
			smallImage[i] = byte(i)
		}
		smallB64 := base64.StdEncoding.EncodeToString(smallImage)
		relPath := persistScreenshot(logger, "test-session-small", "wf-small", 0, smallB64)
		if relPath == "" {
			t.Fatal("expected non-empty relPath for small but valid image")
		}
		absPath := filepath.Join(tmpDir, "test-session-small", relPath)
		data, err := os.ReadFile(absPath)
		if err != nil {
			t.Fatalf("failed to read file: %v", err)
		}
		if len(data) != 100 {
			t.Errorf("expected 100 bytes, got %d", len(data))
		}
	})

	t.Run("empty session ID", func(t *testing.T) {
		relPath := persistScreenshot(logger, "", "wf-nosess", 0, b64Data)
		if relPath != "" {
			t.Errorf("expected empty relPath for empty session, got %s", relPath)
		}
	})

	t.Run("path traversal session ID", func(t *testing.T) {
		relPath := persistScreenshot(logger, "../etc/passwd", "wf-evil", 0, b64Data)
		if relPath != "" {
			t.Errorf("expected empty relPath for path traversal, got %s", relPath)
		}
	})

	t.Run("workflow ID suffix truncation", func(t *testing.T) {
		relPath := persistScreenshot(logger, "test-session-trunc", "very-long-workflow-id-1234567890", 0, b64Data)
		if relPath == "" {
			t.Fatal("expected non-empty relPath")
		}
		if !strings.Contains(relPath, "34567890") {
			t.Errorf("expected workflow suffix '34567890' in path, got %s", relPath)
		}
	})

	t.Run("base64 with whitespace and newlines", func(t *testing.T) {
		// Insert newlines every 76 chars (MIME-style) and some spaces
		var withNewlines strings.Builder
		for i, c := range b64Data {
			if i > 0 && i%76 == 0 {
				withNewlines.WriteByte('\n')
			}
			withNewlines.WriteByte(byte(c))
		}
		relPath := persistScreenshot(logger, "test-session-ws", "wf-ws", 0, withNewlines.String())
		if relPath == "" {
			t.Fatal("expected non-empty relPath for base64 with whitespace")
		}
		absPath := filepath.Join(tmpDir, "test-session-ws", relPath)
		data, err := os.ReadFile(absPath)
		if err != nil {
			t.Fatalf("failed to read file: %v", err)
		}
		if len(data) != len(fakeImage) {
			t.Errorf("expected %d bytes, got %d", len(fakeImage), len(data))
		}
	})

	t.Run("URL-safe base64 variant", func(t *testing.T) {
		urlSafeB64 := base64.URLEncoding.EncodeToString(fakeImage)
		relPath := persistScreenshot(logger, "test-session-url", "wf-url", 0, urlSafeB64)
		if relPath == "" {
			t.Fatal("expected non-empty relPath for URL-safe base64")
		}
		absPath := filepath.Join(tmpDir, "test-session-url", relPath)
		data, err := os.ReadFile(absPath)
		if err != nil {
			t.Fatalf("failed to read file: %v", err)
		}
		if len(data) != len(fakeImage) {
			t.Errorf("expected %d bytes, got %d", len(fakeImage), len(data))
		}
	})
}

func TestExtractScreenshotPathsFromMetadata(t *testing.T) {
	t.Run("extracts paths from tool_execution_records", func(t *testing.T) {
		meta := map[string]interface{}{
			"tool_execution_records": []interface{}{
				map[string]interface{}{
					"tool":    "browser",
					"success": true,
					"output": map[string]interface{}{
						"action":          "screenshot",
						"screenshot":      "[stored:screenshots/123_0.png]",
						"screenshot_path": "screenshots/123_0.png",
					},
				},
				map[string]interface{}{
					"tool":    "browser",
					"success": true,
					"output": map[string]interface{}{
						"action": "navigate",
						"url":    "https://example.com",
					},
				},
				map[string]interface{}{
					"tool":    "browser",
					"success": true,
					"output": map[string]interface{}{
						"action":          "screenshot",
						"screenshot_path": "screenshots/456_0.png",
					},
				},
			},
		}
		paths := extractScreenshotPathsFromMetadata(meta)
		if len(paths) != 2 {
			t.Fatalf("expected 2 paths, got %d: %v", len(paths), paths)
		}
		if paths[0] != "screenshots/123_0.png" {
			t.Errorf("expected screenshots/123_0.png, got %s", paths[0])
		}
		if paths[1] != "screenshots/456_0.png" {
			t.Errorf("expected screenshots/456_0.png, got %s", paths[1])
		}
	})

	t.Run("returns nil for no metadata", func(t *testing.T) {
		if paths := extractScreenshotPathsFromMetadata(nil); paths != nil {
			t.Errorf("expected nil, got %v", paths)
		}
	})

	t.Run("returns nil when no browser screenshots", func(t *testing.T) {
		meta := map[string]interface{}{
			"tool_execution_records": []interface{}{
				map[string]interface{}{
					"tool":    "web_search",
					"success": true,
					"output":  map[string]interface{}{"results": "..."},
				},
			},
		}
		if paths := extractScreenshotPathsFromMetadata(meta); paths != nil {
			t.Errorf("expected nil, got %v", paths)
		}
	})
}
