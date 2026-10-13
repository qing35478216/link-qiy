package server

import (
	"net/http"
	"net/http/httptest"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/linkai/gateway/internal/config"
	"github.com/linkai/gateway/internal/domain"
)

// TestLatencyBudgetP99 验证工单验收标准 5：转发延迟 P99 < 50ms。
//
// 测量方式：起真实 httptest 上游与网关监听端口，走完整 TCP + HTTP 链路，
// 采样 N 次记录每次往返耗时，取 P99。
//
// 为什么不用 Benchmark（ns/op）：Benchmark 给的是平均值，
// 而验收标准要的是 P99——平均值会掩盖长尾，而长尾恰恰是网关这类
// 入口组件最容易出问题的地方。
func TestLatencyBudgetP99(t *testing.T) {
	if testing.Short() {
		t.Skip("latency benchmark skipped in short mode")
	}

	// 上游：即时返回，隔离出网关自身的开销。
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	cfg := &config.Config{
		JWTSecret:          testSecret,
		TenantRate:         1000000,
		TenantWindow:       time.Hour,
		KeyRate:            1000000,
		KeyWindow:          time.Hour,
		EndpointRate:       1000000,
		EndpointWindow:     time.Hour,
		CORSServiceOrigins: []string{"https://api.link-ai.tech"},
		Upstreams: []config.UpstreamConfig{
			{Name: "runtime", Target: upstream.URL, Surface: string(domain.SurfaceService)},
		},
		Routes: []config.RouteConfig{
			{Method: "POST", PathPrefix: "/service/v1/chat", Upstream: "runtime"},
		},
	}

	srv, err := New(Deps{Cfg: cfg})
	if err != nil {
		t.Fatalf("assemble gateway: %v", err)
	}

	// 通过真实监听端口访问，确保覆盖 HTTP 栈而非直接调用 handler。
	gateway := httptest.NewServer(srv.Handler())
	defer gateway.Close()

	token := signTokenForBench(t)

	const samples = 500
	latencies := make([]time.Duration, 0, samples)
	client := &http.Client{Timeout: 5 * time.Second}

	// 前 50 次预热：建立连接池、让令牌桶与 GC 进入稳态。
	for i := 0; i < 50; i++ {
		doSample(t, client, gateway.URL, token)
	}

	var mu sync.Mutex
	for i := 0; i < samples; i++ {
		d := doSample(t, client, gateway.URL, token)
		mu.Lock()
		latencies = append(latencies, d)
		mu.Unlock()
	}

	sort.Slice(latencies, func(i, j int) bool { return latencies[i] < latencies[j] })
	p50 := latencies[len(latencies)*50/100]
	p99 := latencies[len(latencies)*99/100]
	maxLat := latencies[len(latencies)-1]

	t.Logf("gateway forward latency over %d samples: p50=%v p99=%v max=%v",
		samples, p50, p99, maxLat)

	const budget = 50 * time.Millisecond
	if p99 >= budget {
		t.Errorf("P99 latency %v exceeds the %v budget", p99, budget)
	}
}

// doSample 发一次请求并返回往返耗时。
func doSample(t *testing.T, client *http.Client, baseURL, token string) time.Duration {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, baseURL+"/service/v1/chat", nil)
	if err != nil {
		t.Fatalf("build request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Origin", "https://api.link-ai.tech")
	req.Header.Set("Content-Type", "application/json")

	start := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	_ = resp.Body.Close()
	elapsed := time.Since(start)

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("unexpected status %d", resp.StatusCode)
	}
	return elapsed
}
