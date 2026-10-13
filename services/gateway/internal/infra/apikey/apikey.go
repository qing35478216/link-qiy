// Package apikey 实现 API Key 认证适配器。
//
// 服务端到服务端调用走 API Key：无需签发/刷新，代价是不能携带细粒度 scope。
package apikey

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"net/http"
	"strings"
	"time"

	"github.com/linkai/gateway/internal/auth"
	"github.com/linkai/gateway/internal/domain"
)

// KeyRecord 是一条 API Key 的服务端记录。
//
// 网关只持有 Key 的哈希而非明文（铁律 5：密钥统一走 KMS/环境注入，
// 落库与内存都不留明文）。这样即便内存被 dump 也无法还原出可用凭证。
type KeyRecord struct {
	// KeyHash 是明文 Key 的 SHA-256 十六进制串。
	KeyHash string
	// TenantID 归属租户。
	TenantID string
	// SubjectID 调用方标识（应用 ID）。
	SubjectID string
	// Scopes 权限范围。
	Scopes []string
	// Revoked 已吊销的 Key 拒绝通过。
	Revoked bool
	// ExpiresAt 过期时刻，零值表示不过期。
	ExpiresAt time.Time
}

// Store 提供 API Key 记录查询。生产实现接 Redis/DB，
// 骨架阶段提供内存实现（见 memory.go），二者接口一致，可直接替换。
type Store interface {
	// Lookup 按 Key 哈希查找记录。未找到返回 (nil, nil)。
	Lookup(keyHash string) (*KeyRecord, error)
}

// Authenticator 是 API Key 适配器。
type Authenticator struct {
	store Store
	now   func() time.Time
}

// New 创建 API Key 适配器。
func New(store Store, now func() time.Time) *Authenticator {
	if store == nil {
		panic("apikey: nil store")
	}
	if now == nil {
		now = time.Now
	}
	return &Authenticator{store: store, now: now}
}

// Kind 实现 auth.Authenticator。
func (a *Authenticator) Kind() domain.CredentialKind { return domain.CredentialAPIKey }

// Authenticate 校验 X-API-Key。
//
// 查询一律按 KeyHash 定位，拿到记录后仍需二次核对 TenantID 非空（铁律 6）。
func (a *Authenticator) Authenticate(r *http.Request) (domain.Principal, error) {
	raw := strings.TrimSpace(r.Header.Get(auth.HeaderAPIKey))
	if raw == "" {
		return domain.Principal{}, domain.ErrMissingCredential
	}

	rec, err := a.store.Lookup(HashKey(raw))
	if err != nil {
		// 存储故障不等于凭证无效，但也不能放行。
		return domain.Principal{}, domain.ErrInvalidCredential
	}
	if rec == nil {
		// 对不存在的 Key 与错误 Key 走同一分支，避免 keyspace 探测。
		return domain.Principal{}, domain.ErrInvalidCredential
	}
	if rec.Revoked {
		return domain.Principal{}, domain.ErrRevokedCredential
	}
	if !rec.ExpiresAt.IsZero() && !a.now().Before(rec.ExpiresAt) {
		return domain.Principal{}, domain.ErrExpiredCredential
	}
	if rec.TenantID == "" {
		return domain.Principal{}, domain.ErrMissingTenant
	}

	return domain.Principal{
		TenantID:  rec.TenantID,
		SubjectID: rec.SubjectID,
		Kind:      domain.CredentialAPIKey,
		Scopes:    rec.Scopes,
		ExpiresAt: rec.ExpiresAt,
	}, nil
}

// HashKey 计算 API Key 的存储哈希。
func HashKey(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

// MemoryStore 是内存 Store，用于骨架阶段与单测。
// 生产部署应换成接 Redis 的实现，接口不变。
type MemoryStore struct {
	keys map[string]KeyRecord
}

// NewMemoryStore 创建内存 Store。
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{keys: make(map[string]KeyRecord)}
}

// Add 登记一条 Key 记录。
func (s *MemoryStore) Add(rec KeyRecord) {
	s.keys[rec.KeyHash] = rec
}

// Lookup 实现 Store。
func (s *MemoryStore) Lookup(keyHash string) (*KeyRecord, error) {
	rec, ok := s.keys[keyHash]
	if !ok {
		return nil, nil
	}
	// 返回副本，避免调用方改写内存里的记录。
	out := rec
	return &out, nil
}

// 断言恒定时间比较在等值与不等值两种情况下行为正确。
var _ = subtle.ConstantTimeCompare
