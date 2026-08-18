package attachments

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func setupTestRedis(t *testing.T) (*redis.Client, *miniredis.Miniredis) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		client.Close()
	})
	return client, mr
}

func TestStore_PutAndGet(t *testing.T) {
	client, _ := setupTestRedis(t)
	store := NewStore(client, 30*time.Minute)

	ctx := context.Background()
	sessionID := "test-session-1"
	data := []byte("fake-image-bytes")
	mediaType := "image/png"
	filename := "test.png"

	// Put
	id, err := store.Put(ctx, sessionID, data, mediaType, filename)
	require.NoError(t, err)
	assert.NotEmpty(t, id)

	// Get
	att, err := store.Get(ctx, id)
	require.NoError(t, err)
	assert.Equal(t, data, att.Data)
	assert.Equal(t, mediaType, att.MediaType)
	assert.Equal(t, filename, att.Filename)
	assert.Equal(t, sessionID, att.SessionID)
}

func TestStore_GetNotFound(t *testing.T) {
	client, _ := setupTestRedis(t)
	store := NewStore(client, 30*time.Minute)

	_, err := store.Get(context.Background(), "nonexistent")
	assert.ErrorIs(t, err, ErrAttachmentNotFound)
}

func TestStore_TTLRefresh(t *testing.T) {
	client, mr := setupTestRedis(t)
	store := NewStore(client, 2*time.Second)

	ctx := context.Background()
	id, err := store.Put(ctx, "s1", []byte("data"), "image/png", "f.png")
	require.NoError(t, err)

	key := "shannon:att:" + id
	mr.FastForward(1500 * time.Millisecond)
	assert.Less(t, mr.TTL(key), 2*time.Second)

	// Get refreshes TTL
	_, err = store.Get(ctx, id)
	require.NoError(t, err)

	assert.Equal(t, 2*time.Second, mr.TTL(key))
}

func TestStore_SessionIsolation(t *testing.T) {
	client, _ := setupTestRedis(t)
	store := NewStore(client, 30*time.Minute)
	ctx := context.Background()

	// Store attachment in session A
	id, err := store.Put(ctx, "session-A", []byte("secret"), "image/png", "secret.png")
	require.NoError(t, err)

	// Same session → allowed
	att, err := store.Get(ctx, id, "session-A")
	require.NoError(t, err)
	assert.Equal(t, []byte("secret"), att.Data)

	// Different session → rejected
	_, err = store.Get(ctx, id, "session-B")
	assert.ErrorIs(t, err, ErrAttachmentNotFound)

	// No session param (internal/admin call) → allowed
	att, err = store.Get(ctx, id)
	require.NoError(t, err)
	assert.Equal(t, "session-A", att.SessionID)

	// Empty string session param → treated as no-check (backward compat)
	att, err = store.Get(ctx, id, "")
	require.NoError(t, err)
	assert.Equal(t, "session-A", att.SessionID)
}

func TestStore_Delete(t *testing.T) {
	client, _ := setupTestRedis(t)
	store := NewStore(client, 30*time.Minute)

	ctx := context.Background()
	id, _ := store.Put(ctx, "s1", []byte("data"), "image/png", "f.png")

	err := store.Delete(ctx, id)
	require.NoError(t, err)

	_, err = store.Get(ctx, id)
	assert.ErrorIs(t, err, ErrAttachmentNotFound)
}
