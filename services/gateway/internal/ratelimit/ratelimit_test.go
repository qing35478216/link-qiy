package ratelimit

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// fakeLimiter 是确定性的限流后端：按 key 计数到 N 即拒绝。
//
// 用它而非真实令牌桶，是为了让"哪个维度先触发"成为可精确断言的事实，
// 而不是依赖时序。
type fakeLimiter struct {
	// counts 记录每个 key 已消费的次数。
	counts map[string]int
	// calls 记录调用顺序，用于断言求值顺序。
	calls []string
}

func newFakeLimiter() *fakeLimiter {
	return &fakeLimiter{counts: make(map[string]int)}
}

func (f *fakeLimiter) Allow(key string, budget Budget) (Decision, error) {
	f.calls = append(f.calls, key)
	f.counts[key]++
	if f.counts[key] > budget.Limit {
		return Decision{
			Allowed:    false,
			Limit:      budget.Limit,
			Remaining:  0,
			RetryAfter: time.Second,
			ResetAt:    time.Now().Add(time.Second),
		}, nil
	}
	return Decision{
		Allowed:   true,
		Limit:     budget.Limit,
		Remaining: budget.Limit - f.counts[key],
		ResetAt:   time.Now().Add(budget.Window),
	}, nil
}

// fixedNow 是测试基准时刻。
var fixedNow = time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)

// subject 返回一个标准测试主体。
func subject() Subject {
	return Subject{
		TenantID:     "tenant-a",
		CredentialID: "app-1/jwt",
		Endpoint:     "POST /service/v1/chat",
		Now:          fixedNow,
	}
}

// TestTenantLimitTriggersIndependently 是工单验收标准 2 的第一类用例：
// 只注册租户级策略时，租户级能独立触发。
func TestTenantLimitTriggersIndependently(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionTenant,
		Budget:    Budget{Limit: 2, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	s := subject()
	for i := 1; i <= 2; i++ {
		d, err := mw.Evaluate(s)
		if err != nil {
			t.Fatalf("request %d: %v", i, err)
		}
		if !d.Allowed {
			t.Fatalf("request %d should be allowed", i)
		}
	}
	d, err := mw.Evaluate(s)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if d.Allowed {
		t.Fatal("3rd request should hit the tenant limit")
	}
	// 所有计数都发生在租户维度上。
	for key := range backend.counts {
		if key[:7] != "tenant:" {
			t.Errorf("unexpected key %q — only tenant dimension should be registered", key)
		}
	}
}

// TestEndpointLimitTriggersIndependently 是工单验收标准 2 的第二类用例：
// 只注册端点级策略时，端点级能独立触发，且不影响其他端点。
func TestEndpointLimitTriggersIndependently(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionEndpoint,
		Budget:    Budget{Limit: 1, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	chat := subject()
	if d, _ := mw.Evaluate(chat); !d.Allowed {
		t.Fatal("first chat request should pass")
	}
	if d, _ := mw.Evaluate(chat); d.Allowed {
		t.Fatal("second chat request should hit the endpoint limit")
	}

	// 另一个端点有独立配额。
	other := subject()
	other.Endpoint = "GET /service/v1/models"
	if d, _ := mw.Evaluate(other); !d.Allowed {
		t.Fatal("a different endpoint must have its own budget")
	}
}

// TestKeyLimitTriggersIndependently 验证凭证级独立触发。
func TestKeyLimitTriggersIndependently(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionKey,
		Budget:    Budget{Limit: 1, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	keyA := subject()
	if d, _ := mw.Evaluate(keyA); !d.Allowed {
		t.Fatal("first request from key A should pass")
	}
	if d, _ := mw.Evaluate(keyA); d.Allowed {
		t.Fatal("second request from key A should hit the key limit")
	}

	// 同租户的另一个 Key 不受影响——这正是凭证级维度的意义：
	// 防止单个 Key 打满整个租户配额。
	keyB := subject()
	keyB.CredentialID = "app-2/jwt"
	if d, _ := mw.Evaluate(keyB); !d.Allowed {
		t.Fatal("a different credential must have its own budget")
	}
}

// TestTenantIsolation 验证租户之间互不影响。
func TestTenantIsolation(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionTenant,
		Budget:    Budget{Limit: 1, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	a := subject()
	for i := 0; i < 2; i++ {
		mw.Evaluate(a) //nolint:errcheck // 测试中忽略返回值
	}
	if d, _ := mw.Evaluate(a); d.Allowed {
		t.Fatal("tenant-a should be exhausted")
	}

	b := subject()
	b.TenantID = "tenant-b"
	if d, _ := mw.Evaluate(b); !d.Allowed {
		t.Fatal("tenant-b must have its own budget")
	}
}

// TestAllDimensionsMustPass 验证任一维度超额即整体拒绝。
func TestAllDimensionsMustPass(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	// 租户宽松，凭证严格。
	for _, p := range []Policy{
		{Dimension: DimensionTenant, Budget: Budget{Limit: 100, Window: time.Minute}, Limiter: backend},
		{Dimension: DimensionKey, Budget: Budget{Limit: 1, Window: time.Minute}, Limiter: backend},
	} {
		if err := reg.Register(p); err != nil {
			t.Fatalf("register: %v", err)
		}
	}
	mw := NewMiddleware(reg, nil)

	s := subject()
	if d, _ := mw.Evaluate(s); !d.Allowed {
		t.Fatal("first request should pass")
	}
	d, err := mw.Evaluate(s)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if d.Allowed {
		t.Fatal("second request must be rejected by the key dimension")
	}
}

// TestDecisionReportsTightestDimension 验证响应头反映最受限的维度。
func TestDecisionReportsTightestDimension(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	for _, p := range []Policy{
		// 租户剩 50，凭证剩 1 → 应报 1。
		{Dimension: DimensionTenant, Budget: Budget{Limit: 100, Window: time.Minute}, Limiter: backend},
		{Dimension: DimensionKey, Budget: Budget{Limit: 2, Window: time.Minute}, Limiter: backend},
	} {
		if err := reg.Register(p); err != nil {
			t.Fatalf("register: %v", err)
		}
	}
	mw := NewMiddleware(reg, nil)

	d, err := mw.Evaluate(subject())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !d.Allowed {
		t.Fatal("first request should be allowed")
	}
	if d.Remaining != 1 {
		t.Fatalf("Remaining = %d, want 1 (the tightest dimension)", d.Remaining)
	}
}

// TestNoPoliciesMeansNoLimit 验证未注册策略时不限流。
func TestNoPoliciesMeansNoLimit(t *testing.T) {
	t.Parallel()

	mw := NewMiddleware(NewPolicyRegistry(), nil)
	for i := 0; i < 100; i++ {
		d, err := mw.Evaluate(subject())
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if !d.Allowed {
			t.Fatal("no policies registered means no limiting")
		}
	}
}

// TestMissingTenantRejected 验证无租户主体被拒（铁律 6）。
func TestMissingTenantRejected(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionTenant,
		Budget:    Budget{Limit: 10, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	s := subject()
	s.TenantID = ""
	if _, err := mw.Evaluate(s); !errors.Is(err, domain.ErrMissingTenant) {
		t.Fatalf("err = %v, want ErrMissingTenant", err)
	}
}

// TestRegisterRejectsInvalidPolicy 验证非法策略被拒。
func TestRegisterRejectsInvalidPolicy(t *testing.T) {
	t.Parallel()

	reg := NewPolicyRegistry()
	cases := []struct {
		name string
		p    Policy
	}{
		{"零配额", Policy{Dimension: DimensionTenant, Budget: Budget{Limit: 0, Window: time.Minute}, Limiter: newFakeLimiter()}},
		{"零窗口", Policy{Dimension: DimensionTenant, Budget: Budget{Limit: 10, Window: 0}, Limiter: newFakeLimiter()}},
		{"无后端", Policy{Dimension: DimensionTenant, Budget: Budget{Limit: 10, Window: time.Minute}}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if err := reg.Register(tc.p); !errors.Is(err, domain.ErrRateLimitMisconfigured) {
				t.Fatalf("err = %v, want ErrRateLimitMisconfigured", err)
			}
		})
	}
}

// TestRegisterRejectsDuplicateDimension 验证同一维度不能注册两次。
func TestRegisterRejectsDuplicateDimension(t *testing.T) {
	t.Parallel()

	reg := NewPolicyRegistry()
	p := Policy{Dimension: DimensionTenant, Budget: Budget{Limit: 1, Window: time.Minute}, Limiter: newFakeLimiter()}
	if err := reg.Register(p); err != nil {
		t.Fatalf("first register: %v", err)
	}
	if err := reg.Register(p); !errors.Is(err, domain.ErrRateLimitMisconfigured) {
		t.Fatalf("err = %v, want ErrRateLimitMisconfigured", err)
	}
}

// TestDimensionsPreserveRegistrationOrder 验证维度顺序稳定可预测。
func TestDimensionsPreserveRegistrationOrder(t *testing.T) {
	t.Parallel()

	reg := NewPolicyRegistry()
	for _, d := range []Dimension{DimensionEndpoint, DimensionTenant, DimensionKey} {
		p := Policy{Dimension: d, Budget: Budget{Limit: 1, Window: time.Minute}, Limiter: newFakeLimiter()}
		if err := reg.Register(p); err != nil {
			t.Fatalf("register: %v", err)
		}
	}
	got := reg.Dimensions()
	want := []Dimension{DimensionEndpoint, DimensionTenant, DimensionKey}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Dimensions() = %v, want %v", got, want)
		}
	}
}

// TestComposeKeyIncludesTenantInEveryDimension 验证每个维度的键都带租户。
//
// 若端点级/凭证级键不含租户，A 租户刷爆端点会连累 B 租户。
func TestComposeKeyIncludesTenantInEveryDimension(t *testing.T) {
	t.Parallel()

	s := subject()
	for _, dim := range []Dimension{DimensionTenant, DimensionKey, DimensionEndpoint} {
		key, ok := composeKey(dim, s)
		if !ok {
			t.Fatalf("dimension %s should be applicable", dim)
		}
		if !strings.Contains(key, "tenant-a") {
			t.Errorf("key for %s = %q, must contain tenant id", dim, key)
		}
	}
}

// TestInapplicableDimensionsAreSkipped 验证缺少输入的维度被跳过而非报错。
func TestInapplicableDimensionsAreSkipped(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionKey,
		Budget:    Budget{Limit: 1, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	// 无凭证指纹时，凭证级维度不适用，应放行而不是报错。
	s := subject()
	s.CredentialID = ""
	for i := 0; i < 5; i++ {
		d, err := mw.Evaluate(s)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if !d.Allowed {
			t.Fatal("inapplicable dimension should not block the request")
		}
	}
	if len(backend.calls) != 0 {
		t.Errorf("limiter should not have been called, got %v", backend.calls)
	}
}

// TestHandleSetsRateLimitHeaders 验证响应头与 429 状态。
func TestHandleSetsRateLimitHeaders(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionTenant,
		Budget:    Budget{Limit: 1, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	mw := NewMiddleware(reg, nil)

	h := mw.Handle(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	// 带上 Principal 的请求才能通过限流（鉴权在链路上游）。
	newReq := func() *http.Request {
		r := httptest.NewRequestWithContext(context.Background(), http.MethodPost, "/service/v1/chat", nil)
		p := domain.Principal{TenantID: "tenant-a", SubjectID: "app-1", Kind: domain.CredentialJWT}
		return r.WithContext(domain.WithPrincipal(r.Context(), p))
	}

	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, newReq())
	if rec.Code != http.StatusOK {
		t.Fatalf("first request status = %d, want 200", rec.Code)
	}
	if got := rec.Header().Get("X-RateLimit-Remaining"); got != "0" {
		t.Errorf("X-RateLimit-Remaining = %q, want 0", got)
	}

	rec = httptest.NewRecorder()
	h.ServeHTTP(rec, newReq())
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("second request status = %d, want 429", rec.Code)
	}
	if got := rec.Header().Get("Retry-After"); got == "" {
		t.Error("429 response should carry Retry-After")
	}
}

// TestHandleWithoutPrincipalReturns500 验证无身份时返回 500 而非 401。
//
// 正常链路里鉴权在前，走到这里说明装配顺序错了——是服务端问题，不是客户端问题。
func TestHandleWithoutPrincipalReturns500(t *testing.T) {
	t.Parallel()

	reg := NewPolicyRegistry()
	mw := NewMiddleware(reg, nil)

	h := mw.Handle(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/x", nil))

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", rec.Code)
	}
}

// TestCustomEndpointFn 验证端点归一化函数可替换。
func TestCustomEndpointFn(t *testing.T) {
	t.Parallel()

	backend := newFakeLimiter()
	reg := NewPolicyRegistry()
	if err := reg.Register(Policy{
		Dimension: DimensionEndpoint,
		Budget:    Budget{Limit: 1, Window: time.Minute},
		Limiter:   backend,
	}); err != nil {
		t.Fatalf("register: %v", err)
	}
	// 把所有路径归一化成同一个端点。
	mw := NewMiddleware(reg, func(*http.Request) string { return "normalized" })

	p := domain.Principal{TenantID: "tenant-a", SubjectID: "app-1", Kind: domain.CredentialJWT}
	for i, path := range []string{"/a", "/b", "/c"} {
		r := httptest.NewRequestWithContext(context.Background(), http.MethodGet, path, nil)
		r = r.WithContext(domain.WithPrincipal(r.Context(), p))
		d, err := mw.Evaluate(Subject{
			TenantID: "tenant-a",
			Endpoint: mw.endpointFn(r),
		})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if i == 0 && !d.Allowed {
			t.Fatal("first request should pass")
		}
		if i > 0 && d.Allowed {
			t.Fatalf("request %d should hit the normalized endpoint limit", i)
		}
	}
}
