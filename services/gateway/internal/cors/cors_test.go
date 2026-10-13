package cors

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/linkai/gateway/internal/domain"
)

// echoHandler 是放行一切的下游处理器，用于观察中间件是否放行。
var echoHandler = http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
})

// TestPoliciesDoNotCrossContaminate 是工单验收标准 3 的核心用例：
// 三组策略互不串染——A 组的允许项在 B 组必须被拒，反之亦然。
func TestPoliciesDoNotCrossContaminate(t *testing.T) {
	t.Parallel()

	// 三组策略刻意配置成互不相同的来源与方法集合。
	consolePolicy, err := NewPolicy(domain.SurfaceConsole,
		WithAllowedOrigins("https://console.link-ai.tech"),
		WithAllowedMethods("GET", "POST"),
		WithAllowedHeaders("Authorization"),
	)
	if err != nil {
		t.Fatalf("console policy: %v", err)
	}
	servicePolicy, err := NewPolicy(domain.SurfaceService,
		WithAllowedOrigins("https://api.link-ai.tech"),
		WithAllowedMethods("POST"),
	)
	if err != nil {
		t.Fatalf("service policy: %v", err)
	}
	embedPolicy, err := NewPolicy(domain.SurfaceEmbed,
		WithAllowedOrigins("*"),
		WithAllowedMethods("POST"),
	)
	if err != nil {
		t.Fatalf("embed policy: %v", err)
	}

	reg := NewRegistry()
	for _, p := range []*Policy{consolePolicy, servicePolicy, embedPolicy} {
		if err := reg.Register(p); err != nil {
			t.Fatalf("register: %v", err)
		}
	}

	cases := []struct {
		name    string
		surface domain.Surface
		origin  string
		want    bool
	}{
		// console 组只认自己的来源。
		{"console 认自己的来源", domain.SurfaceConsole, "https://console.link-ai.tech", true},
		{"console 拒绝 service 来源", domain.SurfaceConsole, "https://api.link-ai.tech", false},
		{"console 拒绝第三方来源", domain.SurfaceConsole, "https://evil.example.com", false},
		// service 组只认自己的来源。
		{"service 认自己的来源", domain.SurfaceService, "https://api.link-ai.tech", true},
		{"service 拒绝 console 来源", domain.SurfaceService, "https://console.link-ai.tech", false},
		// embed 组通配，但不能反过来让 console 也通配。
		{"embed 接受任意来源", domain.SurfaceEmbed, "https://any.example.com", true},
		{"embed 不影响 console 判定", domain.SurfaceConsole, "https://any.example.com", false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			policy, ok := reg.Lookup(tc.surface)
			if !ok {
				t.Fatalf("no policy for surface %q", tc.surface)
			}
			if got := policy.AllowsOrigin(tc.origin); got != tc.want {
				t.Errorf("AllowsOrigin(%s) on %s = %v, want %v", tc.origin, tc.surface, got, tc.want)
			}
		})
	}
}

// TestMethodsDoNotCrossContaminate 验证方法白名单也不串染。
func TestMethodsDoNotCrossContaminate(t *testing.T) {
	t.Parallel()

	consolePolicy, _ := NewPolicy(domain.SurfaceConsole,
		WithAllowedOrigins("https://console.link-ai.tech"),
		WithAllowedMethods("GET", "POST"),
	)
	servicePolicy, _ := NewPolicy(domain.SurfaceService,
		WithAllowedOrigins("https://api.link-ai.tech"),
		WithAllowedMethods("DELETE"),
	)

	if !consolePolicy.AllowsMethod("GET") {
		t.Error("console should allow GET")
	}
	if consolePolicy.AllowsMethod("DELETE") {
		t.Error("console must NOT allow DELETE (only service group does)")
	}
	if !servicePolicy.AllowsMethod("DELETE") {
		t.Error("service should allow DELETE")
	}
	if servicePolicy.AllowsMethod("GET") {
		t.Error("service must NOT allow GET (only console group does)")
	}
}

// TestMiddlewareRespectsSurfaceFromContext 验证中间件按 context 中的入口面求值。
func TestMiddlewareRespectsSurfaceFromContext(t *testing.T) {
	t.Parallel()

	consolePolicy, _ := NewPolicy(domain.SurfaceConsole,
		WithAllowedOrigins("https://console.link-ai.tech"),
		WithAllowedMethods("GET"),
	)
	reg := NewRegistry()
	if err := reg.Register(consolePolicy); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg)

	// console 入口面 + console 来源 → 应写 CORS 头。
	rec := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/console/api/v1/apps", nil)
	r.Header.Set("Origin", "https://console.link-ai.tech")
	r = r.WithContext(domain.WithSurface(r.Context(), domain.SurfaceConsole))
	mw.Handle(echoHandler).ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "https://console.link-ai.tech" {
		t.Errorf("Allow-Origin = %q, want console origin", got)
	}

	// 同一入口面 + 陌生来源 → 不应写 CORS 头，但请求本身仍要正常响应。
	rec = httptest.NewRecorder()
	r = httptest.NewRequest(http.MethodGet, "/console/api/v1/apps", nil)
	r.Header.Set("Origin", "https://evil.example.com")
	r = r.WithContext(domain.WithSurface(r.Context(), domain.SurfaceConsole))
	mw.Handle(echoHandler).ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("disallowed origin should get no CORS header, got %q", got)
	}
	if rec.Code != http.StatusOK {
		t.Errorf("request should still be served, got status %d", rec.Code)
	}
}

// TestPreflightShortCircuits 验证预检请求返回 204 且不触达下游。
func TestPreflightShortCircuits(t *testing.T) {
	t.Parallel()

	policy, _ := NewPolicy(domain.SurfaceEmbed,
		WithAllowedOrigins("*"),
		WithAllowedMethods("POST"),
		WithAllowedHeaders("Content-Type"),
		WithMaxAge(300),
	)
	reg := NewRegistry()
	if err := reg.Register(policy); err != nil {
		t.Fatalf("register: %v", err)
	}

	downstreamCalled := false
	downstream := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		downstreamCalled = true
		w.WriteHeader(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodOptions, "/embed/v1/chat", nil)
	r.Header.Set("Origin", "https://third-party.example.com")
	r.Header.Set("Access-Control-Request-Method", "POST")
	r.Header.Set("Access-Control-Request-Headers", "Content-Type")
	r = r.WithContext(domain.WithSurface(r.Context(), domain.SurfaceEmbed))

	NewMiddleware(reg).Handle(downstream).ServeHTTP(rec, r)

	if rec.Code != http.StatusNoContent {
		t.Errorf("preflight status = %d, want 204", rec.Code)
	}
	if downstreamCalled {
		t.Error("preflight must not reach downstream handler")
	}
	if got := rec.Header().Get("Access-Control-Max-Age"); got != "300" {
		t.Errorf("Max-Age = %q, want 300", got)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Errorf("Allow-Origin = %q, want *", got)
	}
}

// TestPreflightRejectsDisallowedHeader 验证预检的头白名单生效。
func TestPreflightRejectsDisallowedHeader(t *testing.T) {
	t.Parallel()

	policy, _ := NewPolicy(domain.SurfaceConsole,
		WithAllowedOrigins("https://console.link-ai.tech"),
		WithAllowedMethods("GET"),
		WithAllowedHeaders("Authorization"),
	)
	reg := NewRegistry()
	if err := reg.Register(policy); err != nil {
		t.Fatalf("register: %v", err)
	}

	// 请求一个未在白名单里的头。
	rec := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodOptions, "/console/api/v1/apps", nil)
	r.Header.Set("Origin", "https://console.link-ai.tech")
	r.Header.Set("Access-Control-Request-Method", "GET")
	r.Header.Set("Access-Control-Request-Headers", "X-Evil-Header")
	r = r.WithContext(domain.WithSurface(r.Context(), domain.SurfaceConsole))

	NewMiddleware(reg).Handle(echoHandler).ServeHTTP(rec, r)

	if rec.Code == http.StatusNoContent {
		t.Error("preflight with disallowed header must not be approved")
	}
	if got := rec.Header().Get("Access-Control-Allow-Headers"); got != "" {
		t.Errorf("disallowed header should yield no Allow-Headers, got %q", got)
	}
}

// TestNoSurfaceInContextMeansNoCORS 验证没有入口面时不写任何 CORS 头。
func TestNoSurfaceInContextMeansNoCORS(t *testing.T) {
	t.Parallel()

	policy, _ := NewPolicy(domain.SurfaceEmbed, WithAllowedOrigins("*"))
	reg := NewRegistry()
	if err := reg.Register(policy); err != nil {
		t.Fatalf("register: %v", err)
	}

	rec := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/anything", nil)
	r.Header.Set("Origin", "https://any.example.com")

	NewMiddleware(reg).Handle(echoHandler).ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("without surface, no CORS header expected, got %q", got)
	}
	if rec.Code != http.StatusOK {
		t.Errorf("request should still be served, got %d", rec.Code)
	}
}

// TestUnregisteredSurfaceMeansNoCORS 验证未注册策略的入口面不写 CORS 头。
func TestUnregisteredSurfaceMeansNoCORS(t *testing.T) {
	t.Parallel()

	// 只注册 console，故意留下 service 未注册。
	consolePolicy, _ := NewPolicy(domain.SurfaceConsole, WithAllowedOrigins("*"))
	reg := NewRegistry()
	if err := reg.Register(consolePolicy); err != nil {
		t.Fatalf("register: %v", err)
	}

	rec := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/service/v1/chat", nil)
	r.Header.Set("Origin", "https://any.example.com")
	r = r.WithContext(domain.WithSurface(r.Context(), domain.SurfaceService))

	NewMiddleware(reg).Handle(echoHandler).ServeHTTP(rec, r)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("unregistered surface must get no CORS header, got %q", got)
	}
}

// TestWildcardWithCredentialsRejected 验证通配来源不得开启凭证。
//
// 规范明令禁止，且放行等于让任意站点带用户 Cookie 打我们的 API。
func TestWildcardWithCredentialsRejected(t *testing.T) {
	t.Parallel()

	_, err := NewPolicy(domain.SurfaceEmbed,
		WithAllowedOrigins("*"),
		WithCredentials(true),
	)
	if err == nil {
		t.Fatal("wildcard origin + credentials must be rejected at construction time")
	}
}

// TestDuplicateSurfaceRejected 验证同一入口面不能注册两组策略。
func TestDuplicateSurfaceRejected(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	p, _ := NewPolicy(domain.SurfaceConsole, WithAllowedOrigins("https://a.example.com"))
	if err := reg.Register(p); err != nil {
		t.Fatalf("first register should succeed: %v", err)
	}
	dup, _ := NewPolicy(domain.SurfaceConsole, WithAllowedOrigins("https://b.example.com"))
	if err := reg.Register(dup); err != domain.ErrDuplicateSurface {
		t.Fatalf("err = %v, want ErrDuplicateSurface", err)
	}
	// 第一组策略必须仍然有效，不被第二组覆盖。
	lookup, _ := reg.Lookup(domain.SurfaceConsole)
	if !lookup.AllowsOrigin("https://a.example.com") {
		t.Error("original policy should be preserved")
	}
}

// TestOriginMatchingIsCaseSensitive 验证来源按规范大小写敏感。
func TestOriginMatchingIsCaseSensitive(t *testing.T) {
	t.Parallel()

	p, _ := NewPolicy(domain.SurfaceConsole,
		WithAllowedOrigins("https://Console.Link-AI.tech"),
	)
	if !p.AllowsOrigin("https://Console.Link-AI.tech") {
		t.Error("exact origin should be allowed")
	}
	if p.AllowsOrigin("https://console.link-ai.tech") {
		t.Error("origin comparison must be case-sensitive")
	}
}

// TestHeaderMatchingIsCaseInsensitive 验证头名比对大小写不敏感。
func TestHeaderMatchingIsCaseInsensitive(t *testing.T) {
	t.Parallel()

	p, _ := NewPolicy(domain.SurfaceConsole, WithAllowedHeaders("Content-Type"))
	if !p.AllowsHeader("content-type") {
		t.Error("header names must match case-insensitively")
	}
	if p.AllowsHeader("x-secret") {
		t.Error("unlisted header must be rejected")
	}
}

// TestEmptyOriginRejected 验证空来源不被视为合法。
func TestEmptyOriginRejected(t *testing.T) {
	t.Parallel()

	p, _ := NewPolicy(domain.SurfaceEmbed, WithAllowedOrigins("*"))
	if p.AllowsOrigin("") {
		t.Error("empty origin must never be allowed")
	}
}

// TestSurfacesAreStable 验证入口面列表顺序稳定。
func TestSurfacesAreStable(t *testing.T) {
	t.Parallel()

	reg := NewRegistry()
	for _, s := range []domain.Surface{domain.SurfaceEmbed, domain.SurfaceConsole, domain.SurfaceService} {
		p, _ := NewPolicy(s, WithAllowedOrigins("*"))
		if err := reg.Register(p); err != nil {
			t.Fatalf("register: %v", err)
		}
	}
	got := reg.Surfaces()
	want := []domain.Surface{domain.SurfaceConsole, domain.SurfaceEmbed, domain.SurfaceService}
	if len(got) != len(want) {
		t.Fatalf("Surfaces() = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Surfaces() = %v, want %v (sorted)", got, want)
		}
	}
}
