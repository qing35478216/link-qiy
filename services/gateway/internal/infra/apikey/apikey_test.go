package apikey

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/linkai/gateway/internal/auth"
	"github.com/linkai/gateway/internal/domain"
)

// fixedNow 是测试基准时刻。
var fixedNow = time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)

// newStoreWithKey 构造一个含一条 API Key 记录的内存 Store。
func newStoreWithKey(rawKey string, rec KeyRecord) *MemoryStore {
	s := NewMemoryStore()
	rec.KeyHash = HashKey(rawKey)
	s.Add(rec)
	return s
}

// requestWithKey 构造一个带 API Key 的请求。
func requestWithKey(key string) *http.Request {
	r := httptest.NewRequest(http.MethodPost, "/service/v1/chat", nil)
	if key != "" {
		r.Header.Set(auth.HeaderAPIKey, key)
	}
	return r
}

// TestAuthenticate_ValidKey 验证合法 Key 通过并解析出租户。
func TestAuthenticate_ValidKey(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-live-abc123", KeyRecord{
		TenantID:  "tenant-a",
		SubjectID: "app-1",
		Scopes:    []string{"app:invoke"},
	})
	a := New(store, func() time.Time { return fixedNow })

	p, err := a.Authenticate(requestWithKey("sk-live-abc123"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p.TenantID != "tenant-a" {
		t.Errorf("TenantID = %q, want tenant-a", p.TenantID)
	}
	if p.SubjectID != "app-1" {
		t.Errorf("SubjectID = %q, want app-1", p.SubjectID)
	}
	if p.Kind != domain.CredentialAPIKey {
		t.Errorf("Kind = %q, want apikey", p.Kind)
	}
}

// TestAuthenticate_UnknownKeyRejected 验证未知 Key 被拒。
func TestAuthenticate_UnknownKeyRejected(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-live-abc123", KeyRecord{TenantID: "tenant-a"})
	a := New(store, nil)

	_, err := a.Authenticate(requestWithKey("sk-live-wrong"))
	if !errors.Is(err, domain.ErrInvalidCredential) {
		t.Fatalf("err = %v, want ErrInvalidCredential", err)
	}
}

// TestAuthenticate_MissingKey 验证缺少 Key 头返回缺失错误。
func TestAuthenticate_MissingKey(t *testing.T) {
	t.Parallel()

	a := New(NewMemoryStore(), nil)
	if _, err := a.Authenticate(requestWithKey("")); !errors.Is(err, domain.ErrMissingCredential) {
		t.Fatalf("err = %v, want ErrMissingCredential", err)
	}
	// 全空白同样视为缺失。
	if _, err := a.Authenticate(requestWithKey("   ")); !errors.Is(err, domain.ErrMissingCredential) {
		t.Fatalf("whitespace key: err = %v, want ErrMissingCredential", err)
	}
}

// TestAuthenticate_RevokedKeyRejected 验证吊销的 Key 被拒。
func TestAuthenticate_RevokedKeyRejected(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-revoked", KeyRecord{
		TenantID: "tenant-a",
		Revoked:  true,
	})
	a := New(store, nil)

	_, err := a.Authenticate(requestWithKey("sk-revoked"))
	if !errors.Is(err, domain.ErrRevokedCredential) {
		t.Fatalf("err = %v, want ErrRevokedCredential", err)
	}
}

// TestAuthenticate_ExpiredKeyRejected 验证过期 Key 被拒。
func TestAuthenticate_ExpiredKeyRejected(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-expired", KeyRecord{
		TenantID:  "tenant-a",
		ExpiresAt: fixedNow.Add(-time.Hour),
	})
	a := New(store, func() time.Time { return fixedNow })

	_, err := a.Authenticate(requestWithKey("sk-expired"))
	if !errors.Is(err, domain.ErrExpiredCredential) {
		t.Fatalf("err = %v, want ErrExpiredCredential", err)
	}
}

// TestAuthenticate_KeyWithoutExpiryNeverExpires 验证未设过期时间的 Key 长期有效。
func TestAuthenticate_KeyWithoutExpiryNeverExpires(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-permanent", KeyRecord{TenantID: "tenant-a"})
	a := New(store, func() time.Time { return fixedNow.Add(1000 * time.Hour) })

	p, err := a.Authenticate(requestWithKey("sk-permanent"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p.TenantID != "tenant-a" {
		t.Errorf("TenantID = %q, want tenant-a", p.TenantID)
	}
}

// TestAuthenticate_RecordWithoutTenantRejected 验证无租户记录被拒（铁律 6）。
func TestAuthenticate_RecordWithoutTenantRejected(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-no-tenant", KeyRecord{SubjectID: "app-1"})
	a := New(store, nil)

	_, err := a.Authenticate(requestWithKey("sk-no-tenant"))
	if !errors.Is(err, domain.ErrMissingTenant) {
		t.Fatalf("err = %v, want ErrMissingTenant", err)
	}
}

// TestAuthenticate_StoreFailureRejected 验证存储故障不放行。
func TestAuthenticate_StoreFailureRejected(t *testing.T) {
	t.Parallel()

	a := New(failingStore{}, nil)
	if _, err := a.Authenticate(requestWithKey("any")); !errors.Is(err, domain.ErrInvalidCredential) {
		t.Fatalf("err = %v, want ErrInvalidCredential", err)
	}
}

// failingStore 是总是返回错误的 Store。
type failingStore struct{}

func (failingStore) Lookup(string) (*KeyRecord, error) { return nil, errors.New("redis down") }

// TestHashKeyIsStable 验证哈希稳定且不泄露明文。
func TestHashKeyIsStable(t *testing.T) {
	t.Parallel()

	h1 := HashKey("sk-live-abc123")
	h2 := HashKey("sk-live-abc123")
	if h1 != h2 {
		t.Error("hash must be deterministic")
	}
	if h1 == "sk-live-abc123" {
		t.Error("hash must not equal the plaintext key")
	}
	if HashKey("sk-live-other") == h1 {
		t.Error("different keys must hash differently")
	}
	// SHA-256 十六进制串定长 64。
	if len(h1) != 64 {
		t.Errorf("hash length = %d, want 64", len(h1))
	}
}

// TestMemoryStoreReturnsCopy 验证 Lookup 返回副本，调用方改写不影响存储。
func TestMemoryStoreReturnsCopy(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-1", KeyRecord{TenantID: "tenant-a"})
	rec, err := store.Lookup(HashKey("sk-1"))
	if err != nil {
		t.Fatalf("lookup: %v", err)
	}
	rec.TenantID = "tenant-hacked"

	again, err := store.Lookup(HashKey("sk-1"))
	if err != nil {
		t.Fatalf("lookup: %v", err)
	}
	if again.TenantID != "tenant-a" {
		t.Fatalf("stored record was mutated: %q", again.TenantID)
	}
}

// TestMemoryStoreLookupMissing 验证查不到时返回 (nil, nil)。
func TestMemoryStoreLookupMissing(t *testing.T) {
	t.Parallel()

	rec, err := NewMemoryStore().Lookup("nonexistent")
	if err != nil {
		t.Fatalf("err = %v, want nil", err)
	}
	if rec != nil {
		t.Fatalf("rec = %v, want nil", rec)
	}
}

// TestNewPanicsOnNilStore 验证 nil Store 在构造期 panic。
func TestNewPanicsOnNilStore(t *testing.T) {
	t.Parallel()

	defer func() {
		if recover() == nil {
			t.Fatal("nil store must panic")
		}
	}()
	New(nil, nil)
}

// TestKeyWhitespaceTrimmed 验证 Key 首尾空白被忽略。
func TestKeyWhitespaceTrimmed(t *testing.T) {
	t.Parallel()

	store := newStoreWithKey("sk-1", KeyRecord{TenantID: "tenant-a"})
	a := New(store, nil)

	r := httptest.NewRequest(http.MethodPost, "/x", nil)
	r.Header.Set(auth.HeaderAPIKey, "  sk-1  ")
	if _, err := a.Authenticate(r); err != nil {
		t.Fatalf("surrounding whitespace should be tolerated, got %v", err)
	}
}
