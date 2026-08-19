package openai

import (
	"bytes"
	"context"
	"net/http"
	"strings"
	"testing"

	"go.uber.org/zap"
)

type flushResponseRecorder struct {
	header http.Header
	body   bytes.Buffer
	status int
}

func newFlushResponseRecorder() *flushResponseRecorder {
	return &flushResponseRecorder{header: make(http.Header)}
}

func (r *flushResponseRecorder) Header() http.Header { return r.header }

func (r *flushResponseRecorder) Write(b []byte) (int, error) { return r.body.Write(b) }

func (r *flushResponseRecorder) WriteHeader(statusCode int) { r.status = statusCode }

func (r *flushResponseRecorder) Flush() {}

func TestStreamer_DoesNotEndOnWorkflowCompletedBeforeFinalOutput(t *testing.T) {
	sse := strings.Join([]string{
		"event: WORKFLOW_COMPLETED",
		`data: {"workflow_id":"wf-1","type":"WORKFLOW_COMPLETED","agent_id":"research","message":"done","seq":1}`,
		"",
		"event: thread.message.completed",
		`data: {"workflow_id":"wf-1","agent_id":"final_output","response":"Hello","seq":2}`,
		"",
		"event: done",
		"data: [DONE]",
		"",
	}, "\n")

	w := newFlushResponseRecorder()
	streamer := NewStreamer(zap.NewNop(), "test-model")
	err := streamer.StreamResponse(context.Background(), strings.NewReader(sse), w, false)
	if err != nil {
		t.Fatalf("StreamResponse error: %v", err)
	}

	if !strings.Contains(w.body.String(), `"content":"Hello"`) {
		t.Fatalf("expected streamed content in output, got:\n%s", w.body.String())
	}
}
