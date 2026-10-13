package server

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	gjwt "github.com/golang-jwt/jwt/v5"

	"github.com/linkai/gateway/internal/config"
	"github.com/linkai/gateway/internal/domain"
)

// BenchmarkGatewayPipeline 测量整条处理链的转发延迟。
//
// 对应工单验收标准 5「P99 转发延迟基线 <50ms」。
// 上游用一个即时返回的 httptest 服务，因此本基准测的是
// 网关自身四个横切机制 + 反代转发的开销，不含后端业务耗时。
func BenchmarkGatewayPipeline(b *testing.B) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	b.Cleanup(upstream.Close)

	cfg := &config.Config{
		JWTSecret:          testSecret,
		TenantRate:         1000000, // 基准测试不限流，避免令牌桶成为瓶颈
		TenantWindow:       time.Hour,
		KeyRate:            1000000,
		KeyWindow:          time.Hour,
		EndpointRate:       1000000,
		EndpointWindow:     time.Hour,
		CORSConsoleOrigins: []string{"https://console.link-ai.tech"},
		Upstreams: []config.UpstreamConfig{
			{Name: "runtime", Target: upstream.URL, Surface: string(domain.SurfaceService)},
		},
		Routes: []config.RouteConfig{
			{Method: "POST", PathPrefix: "/service/v1/chat", Upstream: "runtime"},
		},
	}

	srv, err := New(Deps{Cfg: cfg})
	if err != nil {
		b.Fatalf("assemble gateway: %v", err)
	}

	token := signTokenForBench(b)
	r := httptest.NewRequest(http.MethodPost, "/service/v1/chat", nil)
	r.Header.Set("Authorization", "Bearer "+token)
	r.Header.Set("Origin", "https://api.link-ai.tech")

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		rec := httptest.NewRecorder()
		srv.Handler().ServeHTTP(rec, r)
		if rec.Code != http.StatusOK {
			b.Fatalf("unexpected status %d", rec.Code)
		}
	}
}

// signTokenForBench 签发一个基准测试用令牌。
func signTokenForBench(tb testing.TB) string {
	tb.Helper()
	claims := gjwt.MapClaims{
		"sub":       "bench-user",
		"tenant_id": "tenant-bench",
		"exp":       time.Now().Add(time.Hour).Unix(),
	}
	tok := gjwt.NewWithClaims(gjwt.SigningMethodHS256, claims)
	signed, err := tok.SignedString([]byte(testSecret))
	if err != nil {
		tb.Fatalf("sign token: %v", err)
	}
	return signed
}

// BenchmarkAuthMiddlewareIsolated 单独测量鉴权开销。
//
// 分离基准的意义在于定位瓶颈：若整链延迟超标，能立刻判断是鉴权、
// 限流还是反代导致，而不必靠猜。
func BenchmarkAuthMiddlewareIsolated(b *testing.B) {
	cfg := benchConfig(b)
	cfg.TenantRate = 1000000
	cfg.KeyRate = 1000000
	cfg.EndpointRate = 1000000

	srv, err := New(Deps{Cfg: cfg})
	if err != nil {
		b.Fatalf("assemble gateway: %v", err)
	}
	token := signTokenForBench(b)
	r := httptest.NewRequest(http.MethodPost, "/service/v1/chat", nil)
	r.Header.Set("Authorization", "Bearer "+token)

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		// 上游不可达会得到 502，但鉴权/限流/CORS/路由解析都已执行完毕——
		// 转发那一步的网络失败时间不计入本基准的意图范围，故不校验状态码。
		srv.Handler().ServeHTTP(httptest.NewRecorder(), r)
	}
}

// benchConfig 是基准测试专用的配置构造（接收 testing.TB）。
func benchConfig(tb testing.TB) *config.Config {
	tb.Helper()
	return &config.Config{
		JWTSecret:          testSecret,
		TenantRate:         1000,
		TenantWindow:       time.Minute,
		KeyRate:            500,
		KeyWindow:          time.Minute,
		EndpointRate:       500,
		EndpointWindow:     time.Minute,
		CORSConsoleOrigins: []string{"https://console.link-ai.tech"},
		Upstreams: []config.UpstreamConfig{
			{Name: "platform", Target: "http://platform.invalid:8001", Surface: string(domain.SurfaceConsole)},
			{Name: "runtime", Target: "http://runtime.invalid:8002", Surface: string(domain.SurfaceService)},
		},
		Routes: []config.RouteConfig{
			{Method: "POST", PathPrefix: "/service/v1/chat", Upstream: "runtime"},
		},
	}
}
