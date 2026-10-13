package proxy

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/linkai/gateway/internal/routing"
)

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
	p := New()
	u := routing.Upstream{Name: "echo", Target: upstream.URL, Surface: "service"}

	r := httptest.NewRequest(http.MethodPost, "/service/v1/chat", strings.NewReader(`{"q":"hi"}`))
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

	p := New()
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
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

	p := New()
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
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

	p := New()
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
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
	p := New()
	r := httptest.NewRequest(http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()
	p.Serve(rec, r, routing.Upstream{Name: "dead", Target: "http://127.0.0.1:1"})

	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", rec.Code)
	}
}

// TestServeReusesProxyPerUpstream 验证同上游复用代理实例。
func TestServeReusesProxyPerUpstream(t *testing.T) {
	t.Parallel()

	p := New()
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
	p := New()
	u := routing.Upstream{Name: "echo", Target: upstream.URL}

	done := make(chan struct{})
	for i := 0; i < 20; i++ {
		go func() {
			defer func() { done <- struct{}{} }()
			r := httptest.NewRequest(http.MethodGet, "/x", nil)
			p.Serve(httptest.NewRecorder(), r, u)
		}()
	}
	for i := 0; i < 20; i++ {
		<-done
	}
}
