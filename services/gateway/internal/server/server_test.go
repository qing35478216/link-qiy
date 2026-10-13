package server

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	gjwt "github.com/golang-jwt/jwt/v5"

	"github.com/linkai/gateway/internal/config"
	"github.com/linkai/gateway/internal/domain"
)

// testSecret 是测试签名密钥。
const testSecret = "integration-test-secret-at-least-32-bytes"

// testConfig 返回一份可用的网关配置。
//
// 三个上游各属不同入口面，用于验证 CORS 按入口面分流。
func testConfig(t *testing.T) *config.Config {
	t.Helper()
	cfg := &config.Config{
		Addr:               ":0",
		JWTSecret:          testSecret,
		TenantRate:         1000,
		TenantWindow:       time.Minute,
		KeyRate:            500,
		KeyWindow:          time.Minute,
		EndpointRate:       500,
		EndpointWindow:     time.Minute,
		CORSConsoleOrigins: []string{"https://console.link-ai.tech"},
		CORSServiceOrigins: []string{"https://api.link-ai.tech"},
		CORSEmbedOrigins:   []string{},
		Upstreams: []config.UpstreamConfig{
			{Name: "platform", Target: "http://platform.invalid:8001", Surface: string(domain.SurfaceConsole)},
			{Name: "runtime", Target: "http://runtime.invalid:8002", Surface: string(domain.SurfaceService)},
			{Name: "embed", Target: "http://embed.invalid:8003", Surface: string(domain.SurfaceEmbed)},
		},
		Routes: []config.RouteConfig{
			{Method: "GET", PathPrefix: "/console/api/v1/apps", Upstream: "platform"},
			{Method: "POST", PathPrefix: "/service/v1/chat", Upstream: "runtime"},
			{Method: "POST", PathPrefix: "/embed/v1/chat", Upstream: "embed"},
		},
	}
	return cfg
}

// signToken 签发一个测试令牌。
func signToken(t *testing.T, tenant string, scopes ...string) string {
	t.Helper()
	now := time.Now()
	claims := gjwt.MapClaims{
		"sub":       "user-1",
		"tenant_id": tenant,
		"exp":       now.Add(time.Hour).Unix(),
		"iat":       now.Unix(),
	}
	if len(scopes) > 0 {
		claims["scopes"] = scopes
	}
	tok := gjwt.NewWithClaims(gjwt.SigningMethodHS256, claims)
	signed, err := tok.SignedString([]byte(testSecret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

// do 发起一次经网关的请求。
func do(t *testing.T, srv *Server, method, path, origin, token string) *httptest.ResponseRecorder {
	t.Helper()
	r := httptest.NewRequestWithContext(context.Background(), method, path, nil)
	if origin != "" {
		r.Header.Set("Origin", origin)
	}
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)
	return rec
}

// newTestServer 装配一个网关实例。
func newTestServer(t *testing.T, cfg *config.Config) *Server {
	t.Helper()
	srv, err := New(Deps{Cfg: cfg})
	if err != nil {
		t.Fatalf("assemble gateway: %v", err)
	}
	return srv
}

// TestHealthEndpointsBypassCrossCutting 验证健康检查不受横切机制影响。
func TestHealthEndpointsBypassCrossCutting(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	for _, path := range []string{"/healthz", "/readyz"} {
		rec := do(t, srv, http.MethodGet, path, "", "")
		if rec.Code != http.StatusOK {
			t.Errorf("%s status = %d, want 200", path, rec.Code)
		}
	}
}

// TestUnauthenticatedRejected 验证无凭证请求被鉴权拦截（401）。
func TestUnauthenticatedRejected(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", "")
	if rec.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", rec.Code)
	}
}

// TestPreflightSucceedsWithoutCredentials 验证 CORS 预检不要求凭证。
//
// 这是装配顺序的关键证明：CORS 必须在鉴权之前，
// 否则所有跨域预检都会 401，浏览器直接判定跨域失败。
func TestPreflightSucceedsWithoutCredentials(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	r := httptest.NewRequestWithContext(context.Background(), http.MethodOptions, "/service/v1/chat", nil)
	r.Header.Set("Origin", "https://api.link-ai.tech")
	r.Header.Set("Access-Control-Request-Method", "POST")
	r.Header.Set("Access-Control-Request-Headers", "Authorization")

	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("preflight status = %d, want 204 (CORS must run before auth)", rec.Code)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "https://api.link-ai.tech" {
		t.Errorf("Allow-Origin = %q, want the service origin", got)
	}
}

// TestCORSPoliciesAreSeparatedPerSurface 是工单验收标准 3 的集成验证：
// 三个入口面对同一来源的判定互不影响。
func TestCORSPoliciesAreSeparatedPerSurface(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	const consoleOrigin = "https://console.link-ai.tech"

	// service 入口面收到 console 来源 → 不应写 service 策略的允许头。
	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	r.Header.Set("Origin", consoleOrigin)
	r.Header.Set("Authorization", "Bearer "+signToken(t, "tenant-a"))
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got == consoleOrigin {
		t.Error("service surface must not honour the console policy's origin")
	}

	// console 入口面收到同一来源 → 应被允许。
	r = httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/console/api/v1/apps", nil)
	r.Header.Set("Origin", consoleOrigin)
	r.Header.Set("Authorization", "Bearer "+signToken(t, "tenant-a"))
	rec = httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != consoleOrigin {
		t.Errorf("console surface should allow its own origin, got %q", got)
	}
}

// TestEmbedAllowsAnyOrigin 验证嵌入入口面通配且不影响其他入口面。
func TestEmbedAllowsAnyOrigin(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	const thirdParty = "https://third-party.example.com"

	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/embed/v1/chat", nil)
	r.Header.Set("Origin", thirdParty)
	r.Header.Set("Authorization", "Bearer "+signToken(t, "tenant-a"))
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Errorf("embed surface Allow-Origin = %q, want *", got)
	}
	// 通配策略不得携带凭证头。
	if got := rec.Header().Get("Access-Control-Allow-Credentials"); got != "" {
		t.Errorf("wildcard policy must not allow credentials, got %q", got)
	}
}

// TestCrossTenantAccessRejected 是铁律 6 的集成验证：
// 用 A 租户令牌声明访问 B 租户必须被拒。
func TestCrossTenantAccessRejected(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	r.Header.Set("Authorization", "Bearer "+signToken(t, "tenant-a"))
	r.Header.Set("X-Tenant-Id", "tenant-victim")

	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want 403 for cross-tenant access", rec.Code)
	}
}

// TestMatchingTenantHeaderAllowed 验证租户头与凭证一致时放行。
func TestMatchingTenantHeaderAllowed(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	r.Header.Set("Authorization", "Bearer "+signToken(t, "tenant-a"))
	r.Header.Set("X-Tenant-Id", "tenant-a")

	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, r)

	// 上游地址不可达，会得到 502 —— 说明请求已通过鉴权/限流/CORS 到达路由层。
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502 (request should reach the proxy)", rec.Code)
	}
}

// TestRateLimitTriggersBeforeProxy 是工单验收标准 2 的集成验证：
// 限流在路由之前触发，因此上游不可达也不影响 429 的可复现性。
func TestRateLimitTriggersBeforeProxy(t *testing.T) {
	t.Parallel()

	cfg := testConfig(t)
	cfg.TenantRate = 3
	cfg.TenantWindow = time.Hour
	cfg.KeyRate = 0      // 关闭凭证级，聚焦租户级
	cfg.EndpointRate = 0 // 关闭端点级
	srv := newTestServer(t, cfg)

	token := signToken(t, "tenant-a")
	// 前三次通过鉴权与限流，落到不可达上游 → 502。
	for i := 1; i <= 3; i++ {
		rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", token)
		if rec.Code != http.StatusBadGateway {
			t.Fatalf("request %d status = %d, want 502 (passed through to proxy)", i, rec.Code)
		}
	}
	// 第四次触发租户级限流。
	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", token)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("4th request status = %d, want 429", rec.Code)
	}
	if got := rec.Header().Get("Retry-After"); got == "" {
		t.Error("429 response should carry Retry-After")
	}
}

// TestEndpointRateLimitIsIndependentOfTenant 验证端点级限流独立于租户级触发。
func TestEndpointRateLimitIsIndependentOfTenant(t *testing.T) {
	t.Parallel()

	cfg := testConfig(t)
	cfg.TenantRate = 10000 // 租户级足够宽松
	cfg.KeyRate = 0
	cfg.EndpointRate = 2
	cfg.EndpointWindow = time.Hour
	srv := newTestServer(t, cfg)

	token := signToken(t, "tenant-a")
	for i := 1; i <= 2; i++ {
		rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", token)
		if rec.Code != http.StatusBadGateway {
			t.Fatalf("request %d status = %d, want 502", i, rec.Code)
		}
	}
	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", token)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("3rd request status = %d, want 429 from the endpoint dimension", rec.Code)
	}
}

// TestTenantIsolationInRateLimit 验证一个租户被限流不影响另一个。
func TestTenantIsolationInRateLimit(t *testing.T) {
	t.Parallel()

	cfg := testConfig(t)
	cfg.TenantRate = 2
	cfg.TenantWindow = time.Hour
	cfg.KeyRate = 0
	cfg.EndpointRate = 0
	srv := newTestServer(t, cfg)

	tokenA := signToken(t, "tenant-a")
	for i := 0; i < 3; i++ {
		do(t, srv, http.MethodPost, "/service/v1/chat", "", tokenA) //nolint:errcheck
	}
	if rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", tokenA); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("tenant-a status = %d, want 429", rec.Code)
	}

	// 另一个租户仍有独立配额。
	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", signToken(t, "tenant-b"))
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("tenant-b status = %d, want 502 (independent quota)", rec.Code)
	}
}

// TestNoRouteReturns404 验证未注册路径返回 404。
func TestNoRouteReturns404(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	rec := do(t, srv, http.MethodGet, "/no/such/path", "", signToken(t, "tenant-a"))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", rec.Code)
	}
}

// TestExpiredTokenRejected 验证过期令牌在集成链路上被拒。
func TestExpiredTokenRejected(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	now := time.Now()
	claims := gjwt.MapClaims{
		"sub":       "user-1",
		"tenant_id": "tenant-a",
		"exp":       now.Add(-time.Hour).Unix(),
	}
	tok := gjwt.NewWithClaims(gjwt.SigningMethodHS256, claims)
	signed, err := tok.SignedString([]byte(testSecret))
	if err != nil {
		t.Fatalf("sign: %v", err)
	}

	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", signed)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 for expired token", rec.Code)
	}
}

// TestAssemblyRejectsInvalidConfig 验证配置非法时装配失败。
func TestAssemblyRejectsInvalidConfig(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name   string
		mutate func(*config.Config)
	}{
		{"JWT 密钥过短", func(c *config.Config) { c.JWTSecret = "short" }},
		{"租户级配额非正", func(c *config.Config) { c.TenantRate = 0 }},
		{"无上游", func(c *config.Config) { c.Upstreams = nil }},
		{"无路由", func(c *config.Config) { c.Routes = nil }},
		{"路由指向未知上游", func(c *config.Config) {
			c.Routes = []config.RouteConfig{{Method: "GET", PathPrefix: "/x", Upstream: "ghost"}}
		}},
		{"console 组通配来源 + 携带凭证", func(c *config.Config) {
			// console 组开启 credentials 时不允许 "*"，
			// 否则任意站点都能带用户 Cookie 打控制台 API。
			c.CORSConsoleOrigins = []string{"*"}
			c.CORSAllowCredentials = true
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := testConfig(t)
			tc.mutate(cfg)
			if _, err := New(Deps{Cfg: cfg}); err == nil {
				t.Fatal("assembly should have failed")
			}
		})
	}
}

// TestAssemblyRejectsNilConfig 验证 nil 配置被拒。
func TestAssemblyRejectsNilConfig(t *testing.T) {
	t.Parallel()

	if _, err := New(Deps{}); err == nil {
		t.Fatal("nil config must be rejected")
	}
}

// TestUpstreamTargetMustBeParseable 验证反代对非法上游地址降级为 502 而非崩溃。
func TestUpstreamTargetMustBeParseable(t *testing.T) {
	t.Parallel()

	cfg := testConfig(t)
	// 明显非法的地址（缺 scheme）。
	cfg.Upstreams[1].Target = "not-a-valid-url"
	srv := newTestServer(t, cfg)

	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", signToken(t, "tenant-a"))
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502 (bad upstream must degrade, not panic)", rec.Code)
	}
}

// TestForwardedRequestCarriesTraceID 验证被转发的请求带上了 trace ID。
//
// 上游故意指向不可解析的 .invalid 域名，请求会止步于 502；
// 断言的是"限流与鉴权都放行了它"，即请求确实走完了前置横切机制。
func TestForwardedRequestPassesCrossCuttingChecks(t *testing.T) {
	t.Parallel()

	srv := newTestServer(t, testConfig(t))
	rec := do(t, srv, http.MethodPost, "/service/v1/chat", "", signToken(t, "tenant-a"))
	if rec.Code == http.StatusTooManyRequests || rec.Code == http.StatusUnauthorized ||
		rec.Code == http.StatusForbidden {
		t.Fatalf("request should pass auth and rate limit, got %d", rec.Code)
	}
}
