package proxy

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/linkai/gateway/internal/routing"
	"github.com/linkai/gateway/internal/ssrf"
)

// testProxy 返回反代实例（单测用）。
func testProxy() *ReverseProxy {
	return New()
}

// echoHeadersUpstream 返回一个把收到的请求头回显成 JSON 的测试上游。
func echoHeadersUpstream(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"path":"`+r.URL.Path+`","method":"`+r.Method+`","host":"`+r.Host+`"}`)
	}))
	t.Cleanup(srv.Close)
	return srv
}

// TestServeForwardsToUpstream 验证请求被转发到上游。
func TestServeForwardsToUpstream(t *testing.T) {
	t.Parallel()

	upstream := echoHeadersUpstream(t)
	p := testProxy()
	u := routing.Upstream{Name: "echo", Target: upstream.URL, Surface: "service"}

	r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", strings.NewReader(`{"q":"hi"}`))
	rec := httptest.NewRecorder()
	p.Serve(rec, r, u)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "/service/v1/chat") {
		t.Errorf("body = %q, want the forwarded path", rec.Body.String())
	}
}

// TestServeStripsTraceparent 验证内部追踪头不被透传给上游。
func TestServeStripsTraceparent(t *testing.T) {
	t.Parallel()

	var received http.Header
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	p := testProxy()
	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil)
	r.Header.Set("traceparent", "00-fake-fake-01")
	p.Serve(httptest.NewRecorder(), r, routing.Upstream{Name: "h", Target: srv.URL})

	if got := received.Get("traceparent"); got != "" {
		t.Errorf("traceparent should be stripped, got %q", got)
	}
}

// TestServeSetsXForwardedFor 验证 X-Forwarded-For 被正确追加。
func TestServeSetsXForwardedFor(t *testing.T) {
	t.Parallel()

	var received http.Header
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	p := testProxy()
	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil)
	p.Serve(httptest.NewRecorder(), r, routing.Upstream{Name: "h", Target: srv.URL})

	if received.Get("X-Forwarded-For") == "" {
		t.Error("X-Forwarded-For should be set by SetXForwarded")
	}
}

// TestServeInvalidTargetDegradesTo502 验证非法上游地址降级为 502 而非 panic。
//
// 上游地址来自启动期配置，解析失败说明配置错了；
// 但配置错误不应让整个网关进程崩溃。
func TestServeInvalidTargetDegradesTo502(t *testing.T) {
	t.Parallel()

	p := testProxy()
	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()

	// 不含 scheme，url.Parse 会失败。
	p.Serve(rec, r, routing.Upstream{Name: "bad", Target: "://not-a-url"})

	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", rec.Code)
	}
}

// TestServeUnreachableUpstreamReturns502 验证上游不可达时返回 502。
func TestServeUnreachableUpstreamReturns502(t *testing.T) {
	t.Parallel()

	// 端口 1 上不会有服务在监听。
	p := testProxy()
	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()
	p.Serve(rec, r, routing.Upstream{Name: "dead", Target: "http://127.0.0.1:1"})

	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", rec.Code)
	}
}

// TestServeReusesProxyPerUpstream 验证同上游复用代理实例。
func TestServeReusesProxyPerUpstream(t *testing.T) {
	t.Parallel()

	p := testProxy()
	u := routing.Upstream{Name: "echo", Target: "http://127.0.0.1:1"}

	first := p.forUpstream(u)
	second := p.forUpstream(u)
	if first != second {
		t.Error("the same upstream should reuse its proxy instance")
	}

	other := routing.Upstream{Name: "other", Target: "http://127.0.0.1:2"}
	if p.forUpstream(other) == first {
		t.Error("different upstreams should get different proxy instances")
	}
}

// TestServeConcurrentSafe 验证并发转发不产生数据竞争。
//
// 上游代理实例是共享可变状态，竞态会导致请求错发到别的上游。
func TestServeConcurrentSafe(t *testing.T) {
	t.Parallel()

	upstream := echoHeadersUpstream(t)
	p := testProxy()
	u := routing.Upstream{Name: "echo", Target: upstream.URL}

	done := make(chan struct{})
	for i := 0; i < 20; i++ {
		go func() {
			defer func() { done <- struct{}{} }()
			r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil)
			p.Serve(httptest.NewRecorder(), r, u)
		}()
	}
	for i := 0; i < 20; i++ {
		<-done
	}
}

// TestClientIPHeadersAreStripped 验证承载客户端 IP 的非标准头被剥离。
//
// 门禁复审发现的缺口：X-Real-IP / X-Client-IP / CF-Connecting-IP /
// True-Client-IP / X-Originating-IP / Forwarded 客户端可伪造，
// 修复前原样透传到下游。下游一旦信任即构成 IP 伪造。
// X-Forwarded-For 不在此列——它由 SetXForwarded() 生成，是可信的。
func TestClientIPHeadersAreStripped(t *testing.T) {
	t.Parallel()

	var received http.Header
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	p := testProxy()
	r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil)
	for _, h := range clientIPHeaders {
		r.Header.Set(h, "6.6.6.6")
	}
	r.Header.Set("X-Forwarded-For", "6.6.6.7") // 应被改写为真实值

	rec := httptest.NewRecorder()
	p.Serve(rec, r, routing.Upstream{Name: "h", Target: srv.URL})

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	for _, h := range clientIPHeaders {
		if got := received.Get(h); got != "" {
			t.Errorf("%s 未被剥离，上游收到 %q", h, got)
		}
	}
	if got := received.Get("X-Forwarded-For"); got == "6.6.6.7" {
		t.Error("伪造的 X-Forwarded-For 应被 SetXForwarded 改写")
	}
}

// TestSsrfGuardIsReusableForUserURLs 守住"SSRF 闸门可用"这件事。
//
// 门禁复审担心：internal/ssrf 零生产引用，将来引入用户可控 URL 的功能
// （webhook / 链接预览）会绕过它。
//
// 注意：闸门**不该**挂到本包的反代上——上游是内部服务，挂上去会把
// 全部上游拦掉（见包注释）。它该被"用户 URL 出站"场景复用。
// 本用例断言闸门已具备被直接复用的能力，即未来功能无需先改造它。
func TestSsrfGuardIsReusableForUserURLs(t *testing.T) {
	t.Parallel()

	g := ssrf.New()
	if g == nil {
		t.Fatal("ssrf.New() must return a usable guard")
	}
	if _, err := g.Validate(context.Background(), "http://127.0.0.1/admin"); err == nil {
		t.Error("闸门必须拦下回环目标")
	}
	if g.Client() == nil {
		t.Error("闸门必须提供可直接使用的出站客户端")
	}
	if g.Transport() == nil {
		t.Error("闸门必须提供加固后的 Transport")
	}
}
