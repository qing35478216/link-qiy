package auth

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// stubAuthenticator 是测试用的认证适配器。
type stubAuthenticator struct {
	kind      domain.CredentialKind
	principal domain.Principal
	err       error
}

// Kind 实现 Authenticator。
func (s *stubAuthenticator) Kind() domain.CredentialKind { return s.kind }

// Authenticate 实现 Authenticator。
func (s *stubAuthenticator) Authenticate(*http.Request) (domain.Principal, error) {
	return s.principal, s.err
}

// fixedNow 是测试基准时刻。
var fixedNow = time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)

// validPrincipal 返回一份合法 Principal。
func validPrincipal() domain.Principal {
	return domain.Principal{
		TenantID:  "tenant-a",
		SubjectID: "user-1",
		Kind:      domain.CredentialJWT,
		ExpiresAt: fixedNow.Add(time.Hour),
	}
}

// bearerRequest 构造一个带 Bearer 令牌的请求。
func bearerRequest(tenantHeader string) *http.Request {
	r := httptest.NewRequest(http.MethodGet, "/console/api/v1/apps", nil)
	r.Header.Set(HeaderAuthorization, "Bearer some-token")
	if tenantHeader != "" {
		r.Header.Set(HeaderTenantID, tenantHeader)
	}
	return r
}

// apiKeyRequest 构造一个带 API Key 的请求。
func apiKeyRequest() *http.Request {
	r := httptest.NewRequest(http.MethodGet, "/service/v1/chat", nil)
	r.Header.Set(HeaderAPIKey, "key-123")
	return r
}

// TestDetectKind 覆盖凭证类型识别的各种组合。
func TestDetectKind(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name      string
		apiKey    string
		authz     string
		wantKind  domain.CredentialKind
		wantFound bool
	}{
		{"无任何凭证", "", "", "", false},
		{"仅 API Key", "k1", "", domain.CredentialAPIKey, true},
		{"仅 Bearer", "", "Bearer t", domain.CredentialJWT, true},
		{"大小写混合 Bearer", "", "bEaReR t", domain.CredentialJWT, true},
		{"空 Bearer 值", "", "Bearer", "", false},
		{"仅空格的 Bearer 值", "", "Bearer    ", "", false},
		{"非 Bearer 方案", "", "Basic abc", "", false},
		{"API Key 优先于 Bearer", "k1", "Bearer t", domain.CredentialAPIKey, true},
		{"空白 API Key 视为缺失", "   ", "Bearer t", domain.CredentialJWT, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			r := httptest.NewRequest(http.MethodGet, "/x", nil)
			if tc.apiKey != "" {
				r.Header.Set(HeaderAPIKey, tc.apiKey)
			}
			if tc.authz != "" {
				r.Header.Set(HeaderAuthorization, tc.authz)
			}
			kind, found := detectKind(r)
			if found != tc.wantFound || kind != tc.wantKind {
				t.Errorf("detectKind = (%q, %v), want (%q, %v)", kind, found, tc.wantKind, tc.wantFound)
			}
		})
	}
}

// TestAuthenticate_Success 验证正常鉴权通过并写入 Principal。
func TestAuthenticate_Success(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
	mw := NewMiddleware(reg, func() time.Time { return fixedNow })

	p, err := mw.Authenticate(bearerRequest(""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p.TenantID != "tenant-a" {
		t.Errorf("TenantID = %q, want tenant-a", p.TenantID)
	}
}

// TestAuthenticate_MissingCredential 验证无凭证返回 401 语义的错误。
func TestAuthenticate_MissingCredential(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
	mw := NewMiddleware(reg, nil)

	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	if _, err := mw.Authenticate(r); !errors.Is(err, domain.ErrMissingCredential) {
		t.Fatalf("err = %v, want ErrMissingCredential", err)
	}
}

// TestAuthenticate_MatchingTenantHeader 声明租户与凭证一致时放行。
func TestAuthenticate_MatchingTenantHeader(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
	mw := NewMiddleware(reg, func() time.Time { return fixedNow })

	if _, err := mw.Authenticate(bearerRequest("tenant-a")); err != nil {
		t.Fatalf("matching tenant header should pass, got %v", err)
	}
}

// TestAuthenticate_TenantMismatchRejected 验证跨租户访问被拒（铁律 6 的核心）。
//
// 这是多租户平台最严重的越权风险：用 A 租户的令牌声明访问 B 租户。
func TestAuthenticate_TenantMismatchRejected(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
	mw := NewMiddleware(reg, func() time.Time { return fixedNow })

	_, err := mw.Authenticate(bearerRequest("tenant-victim"))
	if !errors.Is(err, domain.ErrTenantMismatch) {
		t.Fatalf("err = %v, want ErrTenantMismatch", err)
	}
}

// TestAuthenticate_MissingTenantRejected 验证无租户的 Principal 被拒（铁律 6）。
func TestAuthenticate_MissingTenantRejected(t *testing.T) {
	t.Parallel()

	p := validPrincipal()
	p.TenantID = ""
	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: p})
	mw := NewMiddleware(reg, nil)

	if _, err := mw.Authenticate(bearerRequest("")); !errors.Is(err, domain.ErrMissingTenant) {
		t.Fatalf("err = %v, want ErrMissingTenant", err)
	}
}

// TestAuthenticate_ExpiredRejected 验证过期凭证被中间件拦截。
func TestAuthenticate_ExpiredRejected(t *testing.T) {
	t.Parallel()

	p := validPrincipal()
	p.ExpiresAt = fixedNow.Add(-time.Minute)
	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: p})

	// 中间件时钟晚于凭证过期时刻。
	mw := NewMiddleware(reg, func() time.Time { return fixedNow })

	if _, err := mw.Authenticate(bearerRequest("")); !errors.Is(err, domain.ErrExpiredCredential) {
		t.Fatalf("err = %v, want ErrExpiredCredential", err)
	}
}

// TestAuthenticate_APIKeyDispatch 验证 API Key 请求分派到对应适配器。
func TestAuthenticate_APIKeyDispatch(t *testing.T) {
	t.Parallel()

	p := validPrincipal()
	p.Kind = domain.CredentialAPIKey
	p.ExpiresAt = time.Time{} // API Key 通常不过期

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialAPIKey, principal: p})
	mw := NewMiddleware(reg, func() time.Time { return fixedNow })

	got, err := mw.Authenticate(apiKeyRequest())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Kind != domain.CredentialAPIKey {
		t.Errorf("Kind = %q, want apikey", got.Kind)
	}
}

// TestAuthenticate_NoAdapterForKind 验证携带凭证但无适配器时按非法凭证处理。
func TestAuthenticate_NoAdapterForKind(t *testing.T) {
	t.Parallel()

	reg := NewRegistry() // 空注册表
	mw := NewMiddleware(reg, nil)

	_, err := mw.Authenticate(bearerRequest(""))
	if !errors.Is(err, domain.ErrInvalidCredential) {
		t.Fatalf("err = %v, want ErrInvalidCredential", err)
	}
}

// TestRegistryPanicsOnDuplicateKind 验证同一凭证类型重复注册会 panic。
func TestRegistryPanicsOnDuplicateKind(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})

	defer func() {
		if recover() == nil {
			t.Fatal("duplicate registration must panic")
		}
	}()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
}

// TestRegistryPanicsOnNilAdapter 验证注册 nil 适配器会 panic。
func TestRegistryPanicsOnNilAdapter(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	defer func() {
		if recover() == nil {
			t.Fatal("nil adapter must panic")
		}
	}()
	reg.Register(nil)
}

// TestMiddlewareStatusCodes 验证各类失败映射到正确的 HTTP 状态码。
func TestMiddlewareStatusCodes(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name       string
		adapterErr error
		tenantHdr  string
		wantStatus int
	}{
		{"凭证缺失", domain.ErrMissingCredential, "", http.StatusUnauthorized},
		{"凭证非法", domain.ErrInvalidCredential, "", http.StatusUnauthorized},
		{"凭证过期", domain.ErrExpiredCredential, "", http.StatusUnauthorized},
		{"凭证吊销", domain.ErrRevokedCredential, "", http.StatusUnauthorized},
		{"无租户", domain.ErrMissingTenant, "", http.StatusUnauthorized},
		{"租户不匹配", nil, "tenant-victim", http.StatusForbidden},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			p := validPrincipal()
			if tc.adapterErr == nil {
				// 租户不匹配场景：适配器成功，由中间件比对租户头时发现。
				p.TenantID = "tenant-a"
			}
			reg := NewRegistry()
			reg.Register(&stubAuthenticator{
				kind:      domain.CredentialJWT,
				principal: p,
				err:       tc.adapterErr,
			})
			mw := NewMiddleware(reg, func() time.Time { return fixedNow })

			called := false
			h := mw.Handle(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				called = true
				w.WriteHeader(http.StatusOK)
			}))

			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, bearerRequest(tc.tenantHdr))

			if rec.Code != tc.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, tc.wantStatus)
			}
			if called {
				t.Error("downstream must not be reached after auth failure")
			}
		})
	}
}

// TestHandleInjectsPrincipal 验证成功路径把 Principal 注入 context。
func TestHandleInjectsPrincipal(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
	mw := NewMiddleware(reg, func() time.Time { return fixedNow })

	var got domain.Principal
	h := mw.Handle(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p, ok := FromContext(r.Context())
		if !ok {
			t.Error("Principal should be in context")
		}
		got = p
		w.WriteHeader(http.StatusOK)
	}))

	h.ServeHTTP(httptest.NewRecorder(), bearerRequest(""))

	if got.TenantID != "tenant-a" {
		t.Errorf("injected TenantID = %q, want tenant-a", got.TenantID)
	}
}

// TestErrorBodyDoesNotLeakReason 验证错误响应体不区分失败原因。
//
// 区分"签名错/过期/吊销"会给攻击者一个凭证状态探测 oracle。
func TestErrorBodyDoesNotLeakReason(t *testing.T) {
	t.Parallel()

	bodies := map[string]string{}
	for _, err := range []error{
		domain.ErrInvalidCredential,
		domain.ErrExpiredCredential,
		domain.ErrRevokedCredential,
		domain.ErrMissingCredential,
	} {
		reg := NewRegistry()
		reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, err: err})
		mw := NewMiddleware(reg, nil)

		rec := httptest.NewRecorder()
		mw.Handle(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {})).
			ServeHTTP(rec, bearerRequest(""))

		bodies[err.Error()] = rec.Body.String()
	}
	for reason, body := range bodies {
		if body != `{"error":"unauthorized"}` {
			t.Errorf("reason %q leaked body %q, want uniform body", reason, body)
		}
	}
}

// TestRegistryKinds 验证注册表能列出已注册类型。
func TestRegistryKinds(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	reg.Register(&stubAuthenticator{kind: domain.CredentialJWT, principal: validPrincipal()})
	reg.Register(&stubAuthenticator{kind: domain.CredentialAPIKey, principal: validPrincipal()})

	if got := len(reg.Kinds()); got != 2 {
		t.Errorf("len(Kinds()) = %d, want 2", got)
	}
}
