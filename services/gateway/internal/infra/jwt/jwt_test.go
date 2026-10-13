package jwt

import (
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	gjwt "github.com/golang-jwt/jwt/v5"

	"github.com/linkai/gateway/internal/auth"
	"github.com/linkai/gateway/internal/domain"
)

// testSecret 是测试签名密钥，长度满足 HS256 要求。
const testSecret = "test-secret-key-at-least-32-bytes-long"

// fixedNow 是测试基准时刻。
var fixedNow = time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)

// signToken 签发一个测试令牌。
func signToken(t *testing.T, secret string, claims gjwt.MapClaims, method gjwt.SigningMethod) string {
	t.Helper()
	tok := gjwt.NewWithClaims(method, claims)
	signed, err := tok.SignedString([]byte(secret))
	if err != nil {
		// 测试辅助函数：签发失败说明测试数据有问题，必须 Fatal。
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

// validClaims 返回一份合法 claim。
func validClaims() gjwt.MapClaims {
	return gjwt.MapClaims{
		"sub":       "user-1",
		"tenant_id": "tenant-a",
		"scopes":    []string{"app:read", "app:write"},
		"iss":       "linkai-platform",
		"exp":       fixedNow.Add(time.Hour).Unix(),
		"iat":       fixedNow.Add(-time.Minute).Unix(),
	}
}

// requestWith 构造一个带 Bearer 令牌的请求。
func requestWith(token string) *http.Request {
	r := httptest.NewRequest(http.MethodGet, "/console/api/v1/apps", nil)
	r.Header.Set(auth.HeaderAuthorization, "Bearer "+token)
	return r
}

// TestAuthenticate_Valid 是工单验收标准 1 的正向用例：合法令牌通过并解析出租户。
func TestAuthenticate_Valid(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Issuer: "linkai-platform", Now: func() time.Time { return fixedNow }})
	token := signToken(t, testSecret, validClaims(), gjwt.SigningMethodHS256)

	p, err := a.Authenticate(requestWith(token))
	if err != nil {
		t.Fatalf("expected success, got %v", err)
	}
	if p.TenantID != "tenant-a" {
		t.Errorf("TenantID = %q, want %q", p.TenantID, "tenant-a")
	}
	if p.SubjectID != "user-1" {
		t.Errorf("SubjectID = %q, want %q", p.SubjectID, "user-1")
	}
	if p.Kind != domain.CredentialJWT {
		t.Errorf("Kind = %q, want %q", p.Kind, domain.CredentialJWT)
	}
	if !p.HasScope("app:write") {
		t.Errorf("expected scope app:write, got %v", p.Scopes)
	}
	if p.IsExpired(fixedNow) {
		t.Error("token should not be expired at fixedNow")
	}
}

// TestAuthenticate_Expired 是工单验收标准 1 的第二类用例：过期令牌被拒。
func TestAuthenticate_Expired(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})
	claims := validClaims()
	claims["exp"] = fixedNow.Add(-time.Second).Unix()
	token := signToken(t, testSecret, claims, gjwt.SigningMethodHS256)

	_, err := a.Authenticate(requestWith(token))
	if err != domain.ErrExpiredCredential {
		t.Fatalf("err = %v, want %v", err, domain.ErrExpiredCredential)
	}
}

// TestAuthenticate_LeewayToleratesSmallSkew 验证 leeway 容忍轻微时钟偏移。
//
// 分布式部署下各节点时钟不可能完全一致，令牌刚过期几秒不应立刻拒绝。
func TestAuthenticate_LeewayToleratesSmallSkew(t *testing.T) {
	t.Parallel()

	a := New(Config{
		Secret: []byte(testSecret),
		Leeway: 30 * time.Second,
		Now:    func() time.Time { return fixedNow },
	})
	claims := validClaims()
	// 令牌在 10 秒前过期，落在 30 秒 leeway 内。
	claims["exp"] = fixedNow.Add(-10 * time.Second).Unix()
	token := signToken(t, testSecret, claims, gjwt.SigningMethodHS256)

	if _, err := a.Authenticate(requestWith(token)); err != nil {
		t.Fatalf("token within leeway should pass, got %v", err)
	}
}

// TestAuthenticate_Tampered 是工单验收标准 1 的第三类用例：篡改签名被拒。
func TestAuthenticate_Tampered(t *testing.T) {
	t.Parallel()

	const otherSecret = "a-completely-different-secret-key-32b"
	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})
	// 用另一个密钥签发 → 签名校验必然失败。
	token := signToken(t, otherSecret, validClaims(), gjwt.SigningMethodHS256)

	_, err := a.Authenticate(requestWith(token))
	if err != domain.ErrInvalidCredential {
		t.Fatalf("err = %v, want %v", err, domain.ErrInvalidCredential)
	}
}

// TestAuthenticate_TamperedPayload 验证改动 payload 也会导致签名不匹配。
func TestAuthenticate_TamperedPayload(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})
	token := signToken(t, testSecret, validClaims(), gjwt.SigningMethodHS256)

	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatalf("malformed token: %s", token)
	}
	// 把 payload 里的 tenant_id 改成别的租户，签名保持不变。
	parts[1] = "eyJ0ZW5hbnRfaWQiOiJhdHRhY2tlciIsInN1YiI6InVzZXItMSJ9"
	tampered := strings.Join(parts, ".")

	_, err := a.Authenticate(requestWith(tampered))
	if err != domain.ErrInvalidCredential {
		t.Fatalf("err = %v, want %v", err, domain.ErrInvalidCredential)
	}
}

// TestAuthenticate_AlgNoneRejected 验证 alg=none 攻击被拒。
//
// 这是 JWT 最经典的漏洞：若不锁定算法，攻击者可用 alg=none 伪造令牌。
// jwt 库本身拒绝签发 none 令牌（测试辅助函数会失败），所以这里手工拼装攻击串，
// 模拟攻击者用任意工具生成的载荷。
func TestAuthenticate_AlgNoneRejected(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})

	// header={"alg":"none","typ":"JWT"}，payload 含有效 claim，signature 为空。
	noneHeader := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"none","typ":"JWT"}`))
	payload, err := json.Marshal(map[string]any{
		"sub":       "attacker",
		"tenant_id": "tenant-victim",
		"exp":       fixedNow.Add(time.Hour).Unix(),
	})
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	attack := noneHeader + "." + base64.RawURLEncoding.EncodeToString(payload) + "."

	if _, err := a.Authenticate(requestWith(attack)); err != domain.ErrInvalidCredential {
		t.Fatalf("alg=none token must be rejected with %v, got %v", domain.ErrInvalidCredential, err)
	}
}

// TestAuthenticate_MissingToken 验证无令牌时返回缺失错误。
func TestAuthenticate_MissingToken(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret)})
	for _, header := range []string{"", "Bearer", "Bearer ", "Basic abc", "bearer"} {
		r := httptest.NewRequest(http.MethodGet, "/x", nil)
		if header != "" {
			r.Header.Set(auth.HeaderAuthorization, header)
		}
		if _, err := a.Authenticate(r); err != domain.ErrMissingCredential {
			t.Errorf("header %q: err = %v, want %v", header, err, domain.ErrMissingCredential)
		}
	}
}

// TestAuthenticate_WrongIssuer 验证签发方不符被拒。
func TestAuthenticate_WrongIssuer(t *testing.T) {
	t.Parallel()

	a := New(Config{
		Secret: []byte(testSecret),
		Issuer: "linkai-platform",
		Now:    func() time.Time { return fixedNow },
	})
	claims := validClaims()
	claims["iss"] = "somebody-else"
	token := signToken(t, testSecret, claims, gjwt.SigningMethodHS256)

	_, err := a.Authenticate(requestWith(token))
	if err != domain.ErrInvalidCredential {
		t.Fatalf("err = %v, want %v", err, domain.ErrInvalidCredential)
	}
}

// TestAuthenticate_MissingTenant 验证缺租户的令牌不产生租户（铁律 6）。
//
// 适配器本身不报错，由 auth 中间件归为 ErrMissingTenant，
// 保证"无租户"在全网关只有一种失败语义。
func TestAuthenticate_MissingTenant(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})
	claims := validClaims()
	delete(claims, "tenant_id")
	token := signToken(t, testSecret, claims, gjwt.SigningMethodHS256)

	p, err := a.Authenticate(requestWith(token))
	if err != nil {
		t.Fatalf("adapter should not error, got %v", err)
	}
	if p.TenantID != "" {
		t.Fatalf("TenantID = %q, want empty", p.TenantID)
	}
}

// TestAuthenticate_NoExpirationRejected 验证无 exp 的令牌被拒。
func TestAuthenticate_NoExpirationRejected(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})
	claims := validClaims()
	delete(claims, "exp")
	token := signToken(t, testSecret, claims, gjwt.SigningMethodHS256)

	if _, err := a.Authenticate(requestWith(token)); err == nil {
		t.Fatal("token without exp must be rejected")
	}
}

// TestAuthenticate_ScopesAsString 验证空格分隔的 scope 字符串也能解析。
func TestAuthenticate_ScopesAsString(t *testing.T) {
	t.Parallel()

	a := New(Config{Secret: []byte(testSecret), Now: func() time.Time { return fixedNow }})
	claims := validClaims()
	claims["scopes"] = "app:read billing:read"
	token := signToken(t, testSecret, claims, gjwt.SigningMethodHS256)

	p, err := a.Authenticate(requestWith(token))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(p.Scopes) != 2 || p.Scopes[0] != "app:read" || p.Scopes[1] != "billing:read" {
		t.Fatalf("Scopes = %v, want [app:read billing:read]", p.Scopes)
	}
}

// TestNew_PanicsOnEmptySecret 验证空密钥在构造期 panic。
func TestNew_PanicsOnEmptySecret(t *testing.T) {
	t.Parallel()

	defer func() {
		if recover() == nil {
			t.Fatal("New with empty secret must panic")
		}
	}()
	New(Config{})
}

// TestConstantTimeEqual 验证恒定时间比较工具。
func TestConstantTimeEqual(t *testing.T) {
	t.Parallel()

	if !ConstantTimeEqual("abc", "abc") {
		t.Error("equal strings should return true")
	}
	if ConstantTimeEqual("abc", "abd") {
		t.Error("different strings should return false")
	}
}
