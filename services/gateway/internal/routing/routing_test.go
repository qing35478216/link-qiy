package routing

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/linkai/gateway/internal/domain"
)

// recordingProxy 是记录调用的假反代，避免单测依赖真实网络。
type recordingProxy struct {
	// calls 记录每次转发的上游名。
	calls []string
	// lastReq 是最后一次转发的请求，用于断言注入的头。
	lastReq *http.Request
}

// Serve 实现 Proxy。
func (p *recordingProxy) Serve(w http.ResponseWriter, r *http.Request, u Upstream) {
	p.calls = append(p.calls, u.Name)
	p.lastReq = r
	w.WriteHeader(http.StatusOK)
}

// buildTable 返回一张含三个上游的路由表。
func buildTable(t *testing.T) *Table {
	t.Helper()
	table := NewTable()
	upstreams := []Upstream{
		{Name: "platform", Target: "http://platform:8001", Surface: domain.SurfaceConsole},
		{Name: "runtime", Target: "http://runtime:8002", Surface: domain.SurfaceService},
		{Name: "model-proxy", Target: "http://model:8003", Surface: domain.SurfaceService, RequiredScopes: []string{"model:invoke"}},
	}
	for _, u := range upstreams {
		if err := table.RegisterUpstream(u); err != nil {
			t.Fatalf("register upstream %s: %v", u.Name, err)
		}
	}
	routes := []Route{
		{Method: "GET", PathPrefix: "/console/api/v1", Upstream: "platform"},
		{Method: "POST", PathPrefix: "/console/api/v1", Upstream: "platform"},
		{Method: "POST", PathPrefix: "/service/v1", Upstream: "runtime"},
		{Method: "POST", PathPrefix: "/service/v1/chat", Upstream: "runtime"},
		{Method: "POST", PathPrefix: "/internal/v1/models/invoke", Upstream: "model-proxy"},
	}
	for _, r := range routes {
		if err := table.RegisterRoute(r); err != nil {
			t.Fatalf("register route %s: %v", r.PathPrefix, err)
		}
	}
	return table
}

// chain 组装完整的 解析 → 转发 链路，返回可驱动的前置处理器。
//
// 与 server 装配层保持一致：CORS/鉴权/限流夹在两者之间，
// 这里不重复它们，只保证两段路由逻辑能被独立验证。
func chain(table *Table, p Proxy) http.Handler {
	resolver := NewResolver(table)
	forwarder := NewMiddleware(p)
	return resolver.Handle(forwarder.Handle(http.NotFoundHandler()))
}

// principalWith 返回一个带租户的 Principal。
func principalWith(tenant string, scopes ...string) domain.Principal {
	return domain.Principal{
		TenantID:  tenant,
		SubjectID: "user-1",
		Kind:      domain.CredentialJWT,
		Scopes:    scopes,
	}
}

// TestRegisterUpstreamRejectsDuplicate 验证同名上游不能重复注册。
func TestRegisterUpstreamRejectsDuplicate(t *testing.T) {
	t.Parallel()

	table := NewTable()
	if err := table.RegisterUpstream(Upstream{Name: "platform", Target: "http://a"}); err != nil {
		t.Fatalf("first register: %v", err)
	}
	err := table.RegisterUpstream(Upstream{Name: "platform", Target: "http://b"})
	if !errors.Is(err, domain.ErrDuplicateRoute) {
		t.Fatalf("err = %v, want ErrDuplicateRoute", err)
	}
}

// TestRegisterRouteRejectsUnknownUpstream 验证路由必须指向已注册上游。
func TestRegisterRouteRejectsUnknownUpstream(t *testing.T) {
	t.Parallel()

	table := NewTable()
	err := table.RegisterRoute(Route{Method: "GET", PathPrefix: "/x", Upstream: "nope"})
	if !errors.Is(err, domain.ErrNoRoute) {
		t.Fatalf("err = %v, want ErrNoRoute", err)
	}
}

// TestRegisterRouteRejectsDuplicate 验证同一方法+前缀不能重复注册。
func TestRegisterRouteRejectsDuplicate(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	err := table.RegisterRoute(Route{Method: "GET", PathPrefix: "/console/api/v1", Upstream: "platform"})
	if !errors.Is(err, domain.ErrDuplicateRoute) {
		t.Fatalf("err = %v, want ErrDuplicateRoute", err)
	}
}

// TestLookupLongestPrefixWins 验证最长前缀优先匹配。
func TestLookupLongestPrefixWins(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	// 两条路由都能匹配 /service/v1/chat，应选更长的那条。
	u, route, ok := table.Lookup("POST", "/service/v1/chat/completions")
	if !ok {
		t.Fatal("expected a match")
	}
	if route.PathPrefix != "/service/v1/chat" {
		t.Errorf("PathPrefix = %q, want the longest match /service/v1/chat", route.PathPrefix)
	}
	if u.Name != "runtime" {
		t.Errorf("upstream = %q, want runtime", u.Name)
	}
}

// TestLookupMethodSensitive 验证方法不匹配时无路由。
func TestLookupMethodSensitive(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	if _, _, ok := table.Lookup("DELETE", "/service/v1/chat"); ok {
		t.Error("DELETE should not match a POST-only route")
	}
}

// TestLookupNoMatch 验证无匹配路由。
func TestLookupNoMatch(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	if _, _, ok := table.Lookup("GET", "/unknown/path"); ok {
		t.Error("unexpected match")
	}
}

// TestLookupTrailingSlashNormalised 验证注册时尾斜杠被归一化。
func TestLookupTrailingSlashNormalised(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	if _, route, ok := table.Lookup("GET", "/console/api/v1/apps"); !ok || route.PathPrefix != "/console/api/v1" {
		t.Errorf("expected normalised match, got ok=%v route=%+v", ok, route)
	}
}

// TestHandleInjectsTenantHeaders 验证网关注入租户与入口面头（铁律 6）。
func TestHandleInjectsTenantHeaders(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	p := &recordingProxy{}
	h := chain(table, p)

	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	r = r.WithContext(domain.WithPrincipal(r.Context(), principalWith("tenant-a")))

	h.ServeHTTP(httptest.NewRecorder(), r)

	if len(p.calls) != 1 || p.calls[0] != "runtime" {
		t.Fatalf("proxy calls = %v, want [runtime]", p.calls)
	}
	if got := p.lastReq.Header.Get(HeaderTenantID); got != "tenant-a" {
		t.Errorf("%s = %q, want tenant-a", HeaderTenantID, got)
	}
	if got := p.lastReq.Header.Get(HeaderSurface); got != string(domain.SurfaceService) {
		t.Errorf("%s = %q, want service", HeaderSurface, got)
	}
	if got := p.lastReq.Header.Get(HeaderSubjectID); got != "user-1" {
		t.Errorf("%s = %q, want user-1", HeaderSubjectID, got)
	}
	if got := p.lastReq.Header.Get(HeaderTraceID); got == "" {
		t.Error("trace id should be injected")
	}
}

// TestHandleSetsSurfaceInContext 验证入口面写入 context 供 CORS 消费。
func TestHandleSetsSurfaceInContext(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	var got domain.Surface
	var ok bool

	capture := proxyFunc(func(w http.ResponseWriter, r *http.Request, _ Upstream) {
		got, ok = domain.SurfaceFrom(r.Context())
		w.WriteHeader(http.StatusOK)
	})
	h := chain(table, capture)

	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/console/api/v1/apps", nil)
	r = r.WithContext(domain.WithPrincipal(r.Context(), principalWith("tenant-a")))
	h.ServeHTTP(httptest.NewRecorder(), r)

	if !ok {
		t.Fatal("surface should be present in context")
	}
	if got != domain.SurfaceConsole {
		t.Errorf("surface = %q, want console", got)
	}
}

// proxyFunc 是函数式 Proxy，便于在测试中注入闭包。
type proxyFunc func(http.ResponseWriter, *http.Request, Upstream)

// Serve 实现 Proxy。
func (f proxyFunc) Serve(w http.ResponseWriter, r *http.Request, u Upstream) { f(w, r, u) }

// TestHandleRejectsMissingTenant 验证无租户请求不得出网（铁律 6）。
func TestHandleRejectsMissingTenant(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	p := &recordingProxy{}
	h := chain(table, p)

	// 请求 context 里没有 Principal。
	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, r)

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", rec.Code)
	}
	if len(p.calls) != 0 {
		t.Error("request without tenant must not be forwarded")
	}
}

// TestHandleRejectsEmptyTenant 验证租户为空的 Principal 同样被拒。
func TestHandleRejectsEmptyTenant(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	p := &recordingProxy{}
	h := chain(table, p)

	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	r = r.WithContext(domain.WithPrincipal(r.Context(), principalWith("")))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, r)

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", rec.Code)
	}
	if len(p.calls) != 0 {
		t.Error("request with empty tenant must not be forwarded")
	}
}

// TestHandleEnforcesRequiredScopes 验证上游的 scope 要求生效。
func TestHandleEnforcesRequiredScopes(t *testing.T) {
	t.Parallel()

	table := buildTable(t)

	cases := []struct {
		name       string
		scopes     []string
		wantStatus int
		wantCall   bool
	}{
		{"有权限", []string{"model:invoke"}, http.StatusOK, true},
		{"无权限", []string{"app:read"}, http.StatusForbidden, false},
		{"空权限", nil, http.StatusForbidden, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			proxy := &recordingProxy{}
			h := chain(table, proxy)

			r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/internal/v1/models/invoke", nil)
			r = r.WithContext(domain.WithPrincipal(r.Context(), principalWith("tenant-a", tc.scopes...)))

			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, r)

			if rec.Code != tc.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, tc.wantStatus)
			}
			if called := len(proxy.calls) > 0; called != tc.wantCall {
				t.Errorf("forwarded = %v, want %v", called, tc.wantCall)
			}
		})
	}
}

// TestHandleNoRouteReturns404 验证无匹配路由返回 404。
func TestHandleNoRouteReturns404(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	p := &recordingProxy{}
	h := chain(table, p)

	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/no/such/route", nil)
	r = r.WithContext(domain.WithPrincipal(r.Context(), principalWith("tenant-a")))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, r)

	if rec.Code != http.StatusNotFound {
		t.Errorf("status = %d, want 404", rec.Code)
	}
	if len(p.calls) != 0 {
		t.Error("unmatched request must not be forwarded")
	}
}

// TestHandleUnmatched 验证兜底处理器返回 404。
func TestHandleUnmatched(t *testing.T) {
	t.Parallel()

	rec := httptest.NewRecorder()
	HandleUnmatched(rec, httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil))

	if rec.Code != http.StatusNotFound {
		t.Errorf("status = %d, want 404", rec.Code)
	}
}

// TestResolverRejectsUnmatchedPath 验证无匹配路径在解析阶段即被拦成 404。
//
// 这一步必须早于鉴权：无路由的请求没有上游，不该消耗鉴权与限流的配额。
func TestResolverRejectsUnmatchedPath(t *testing.T) {
	t.Parallel()

	p := &recordingProxy{}
	h := chain(buildTable(t), p)

	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/no/such/path", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, r)

	if rec.Code != http.StatusNotFound {
		t.Errorf("status = %d, want 404", rec.Code)
	}
	if len(p.calls) != 0 {
		t.Error("unmatched request must not be forwarded")
	}
}

// TestResolverMarksSurfaceWithoutPrincipal 验证解析阶段即可读出入口面。
//
// 这是 CORS 能排在鉴权之前的前提：预检请求没有凭证，
// 但仍需按入口面套用正确的跨域策略。
func TestResolverMarksSurfaceWithoutPrincipal(t *testing.T) {
	t.Parallel()

	var got domain.Surface
	var ok bool

	table := buildTable(t)
	// 只跑解析段，止步于一个读取 Surface 的处理器。
	resolver := NewResolver(table)
	probe := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		s, ok2 := domain.SurfaceFrom(r.Context())
		got, ok = s, ok2
		w.WriteHeader(http.StatusOK)
	})
	resolver.Handle(probe).ServeHTTP(httptest.NewRecorder(),
		httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/console/api/v1/apps", nil))

	if !ok || got != domain.SurfaceConsole {
		t.Fatalf("surface = %q (found=%v), want console", got, ok)
	}
}

// TestUpstreamsSorted 验证上游名输出稳定。
func TestUpstreamsSorted(t *testing.T) {
	t.Parallel()

	got := buildTable(t).Upstreams()
	want := []string{"model-proxy", "platform", "runtime"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Upstreams() = %v, want %v", got, want)
		}
	}
}

// TestRegisterUpstreamRejectsEmptyFields 验证上游必须填齐名称与地址。
func TestRegisterUpstreamRejectsEmptyFields(t *testing.T) {
	t.Parallel()

	table := NewTable()
	for _, u := range []Upstream{{Name: "", Target: "http://a"}, {Name: "a", Target: ""}} {
		if err := table.RegisterUpstream(u); !errors.Is(err, domain.ErrNoRoute) {
			t.Errorf("upstream %+v: err = %v, want ErrNoRoute", u, err)
		}
	}
}

// TestNewTraceIDUnique 验证 trace ID 不重复且长度固定。
func TestNewTraceIDUnique(t *testing.T) {
	t.Parallel()

	seen := make(map[string]struct{})
	for i := 0; i < 1000; i++ {
		id := NewTraceID()
		if _, dup := seen[id]; dup {
			t.Fatalf("duplicate trace id generated: %s", id)
		}
		seen[id] = struct{}{}
	}
	if len(NewTraceID()) != 32 {
		t.Error("trace id should be 32 hex chars")
	}
}

// TestPreservesIncomingTraceID 验证已有的 trace ID 不被覆盖。
func TestPreservesIncomingTraceID(t *testing.T) {
	t.Parallel()

	table := buildTable(t)
	p := &recordingProxy{}
	h := chain(table, p)

	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
	r.Header.Set(HeaderTraceID, "upstream-trace-123")
	r = r.WithContext(domain.WithPrincipal(r.Context(), principalWith("tenant-a")))

	h.ServeHTTP(httptest.NewRecorder(), r)

	if got := p.lastReq.Header.Get(HeaderTraceID); got != "upstream-trace-123" {
		t.Errorf("trace id = %q, want the incoming one preserved", got)
	}
}
