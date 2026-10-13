// Package ratelimit 实现网关的限流横切机制（三角之二）。
//
// 职责边界：本包只回答"这次请求超预算了吗"。它通过 context 读取 auth 写入的
// Principal，但绝不 import auth 包——耦合方向是 context 约定，不是包依赖。
// 这样限流可以脱离鉴权单独测试（传入裸 Principal），反之亦然。
package ratelimit

import (
	"context"
	"net/http"
	"strconv"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// Dimension 是限流维度。三个维度独立计数、独立触发、独立配置。
type Dimension string

const (
	// DimensionTenant 租户级：同一租户下所有调用方共享配额。
	DimensionTenant Dimension = "tenant"
	// DimensionKey 凭证级：同一 API Key 单独计数，防单 Key 打满整个租户配额。
	DimensionKey Dimension = "key"
	// DimensionEndpoint 端点级：同一租户在同一端点上的调用量。
	DimensionEndpoint Dimension = "endpoint"
)

// Decision 是一次限流判定结果。
type Decision struct {
	// Allowed 是否放行。
	Allowed bool
	// Limit 该维度的配额上限。
	Limit int
	// Remaining 剩余配额。
	Remaining int
	// RetryAfter 建议的重试等待时长，Allowed 时为 0。
	RetryAfter time.Duration
	// ResetAt 配额恢复时刻。
	ResetAt time.Time
}

// Budget 描述某一维度的配额上限。
type Budget struct {
	// Limit 时间窗口内允许的请求数。
	Limit int
	// Window 时间窗口长度。
	Window time.Duration
}

// Validate 校验预算配置合法性。
func (b Budget) Validate() error {
	if b.Limit <= 0 {
		return domain.ErrRateLimitMisconfigured
	}
	if b.Window <= 0 {
		return domain.ErrRateLimitMisconfigured
	}
	return nil
}

// Limiter 是限流后端接口（铁律 4：新存储 = 新适配器 + 注册，不改内核）。
// 骨架阶段用内存令牌桶，生产可换 Redis 实现而不触碰本包的中间件逻辑。
type Limiter interface {
	// Allow 尝试消费一个配额。key 是已含维度的复合键。
	Allow(key string, budget Budget) (Decision, error)
}

// Policy 把"哪个维度、用什么预算、谁提供后端"绑在一起。
type Policy struct {
	// Dimension 限流维度。
	Dimension Dimension
	// Budget 配额。
	Budget Budget
	// Limiter 后端实现。
	Limiter Limiter
}

// PolicyRegistry 是限流策略注册表。每个维度注册一条策略，
// 重复注册 panic——策略装配错误必须在启动期暴露。
type PolicyRegistry struct {
	policies map[Dimension]Policy
	// order 固定求值顺序，保证响应头与错误的确定性。
	order []Dimension
}

// NewPolicyRegistry 创建空注册表。
func NewPolicyRegistry() *PolicyRegistry {
	return &PolicyRegistry{policies: make(map[Dimension]Policy)}
}

// Register 注册一条维度策略。配置非法或同一维度重复注册都返回错误，
// 由启动期装配代码处理——策略表来自配置，配置错误应可诊断而非 panic。
func (r *PolicyRegistry) Register(p Policy) error {
	if err := p.Budget.Validate(); err != nil {
		return err
	}
	if p.Limiter == nil {
		return domain.ErrRateLimitMisconfigured
	}
	if _, dup := r.policies[p.Dimension]; dup {
		return domain.ErrRateLimitMisconfigured
	}
	r.policies[p.Dimension] = p
	r.order = append(r.order, p.Dimension)
	return nil
}

// Dimensions 返回已注册的维度，按注册顺序。
func (r *PolicyRegistry) Dimensions() []Dimension {
	out := make([]Dimension, len(r.order))
	copy(out, r.order)
	return out
}

// lookup 内部取策略。
func (r *PolicyRegistry) lookup(d Dimension) (Policy, bool) {
	p, ok := r.policies[d]
	return p, ok
}

// Subject 是限流判定所需的最小输入集合。
//
// 刻意只要求"租户 + 凭证指纹 + 端点"，不要求整个 domain.Principal：
// 限流不需要知道用户权限，也就不该依赖鉴权层的类型。
type Subject struct {
	// TenantID 租户。
	TenantID string
	// CredentialID 凭证指纹（API Key 哈希或 JWT jti/sub），可为空则跳过 Key 维度。
	CredentialID string
	// Endpoint 归一化端点标识，如 "POST /service/v1/chat"。
	Endpoint string
	// Now 当前时刻，便于测试注入。
	Now time.Time
}

// Middleware 是限流中间件。与 auth.Middleware 无 import 依赖。
type Middleware struct {
	registry *PolicyRegistry
	// endpointFn 从请求推导端点标识，缺省用 "METHOD path"。
	endpointFn func(r *http.Request) string
}

// NewMiddleware 组装限流中间件。endpointFn 为 nil 时使用 "METHOD path"。
func NewMiddleware(reg *PolicyRegistry, endpointFn func(r *http.Request) string) *Middleware {
	if endpointFn == nil {
		endpointFn = defaultEndpoint
	}
	return &Middleware{registry: reg, endpointFn: endpointFn}
}

// defaultEndpoint 是默认端点归一化函数。
func defaultEndpoint(r *http.Request) string {
	return r.Method + " " + r.URL.Path
}

// Handle 执行限流。所有已注册维度都必须通过，任一维度超额即拒绝。
func (m *Middleware) Handle(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p, ok := PrincipalFromContext(r.Context())
		if !ok {
			// 没有身份就无法定租户配额（铁律 6）。网关的正常链路是鉴权在前，
			// 走到这里说明装配顺序错了，属于 500 而非 401。
			http.Error(w, `{"error":"internal: unauthenticated"}`, http.StatusInternalServerError)
			return
		}

		subject := Subject{
			TenantID:     p.TenantID,
			CredentialID: p.SubjectID + "/" + string(p.Kind),
			Endpoint:     m.endpointFn(r),
			Now:          time.Now(),
		}

		decision, err := m.Evaluate(subject)
		if err != nil {
			http.Error(w, `{"error":"internal: ratelimit"}`, http.StatusInternalServerError)
			return
		}
		writeRateLimitHeaders(w, decision)

		if !decision.Allowed {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(`{"error":"rate_limited"}`))
			return
		}
		next.ServeHTTP(w, r)
	})
}

// Evaluate 对单个 Subject 求值，是可脱离 http 独立测试的核心。
//
// 求值顺序按注册顺序：租户 → 凭证 → 端点。返回的 Decision 取"最紧"的那个，
// 即任何维度超额都拒绝，且响应头反映最受限的那个维度。
func (m *Middleware) Evaluate(s Subject) (Decision, error) {
	if s.TenantID == "" {
		return Decision{}, domain.ErrMissingTenant
	}

	agg := Decision{Allowed: true, Remaining: -1}
	seen := false

	for _, dim := range m.registry.order {
		policy, ok := m.registry.lookup(dim)
		if !ok {
			continue
		}
		key, applicable := composeKey(dim, s)
		if !applicable {
			continue
		}

		d, err := policy.Limiter.Allow(key, policy.Budget)
		if err != nil {
			return Decision{}, err
		}
		seen = true

		// 任一维度拒绝即整体拒绝。
		if !d.Allowed {
			return d, nil
		}
		// 取最紧维度：Remaining 越小越紧，首次为 -1 表示尚未赋值。
		if agg.Remaining == -1 || d.Remaining < agg.Remaining {
			agg = d
			agg.Allowed = true
		}
	}

	if !seen {
		// 一条策略都没注册 = 不限流。这是显式的"关闭限流"，不是错误。
		return Decision{Allowed: true, Remaining: -1}, nil
	}
	return agg, nil
}

// composeKey 按维度合成限流键。不适用的维度返回 applicable=false。
func composeKey(dim Dimension, s Subject) (string, bool) {
	switch dim {
	case DimensionTenant:
		return "tenant:" + s.TenantID, true
	case DimensionKey:
		if s.CredentialID == "" {
			return "", false
		}
		return "key:" + s.TenantID + ":" + s.CredentialID, true
	case DimensionEndpoint:
		if s.Endpoint == "" {
			return "", false
		}
		return "endpoint:" + s.TenantID + ":" + s.Endpoint, true
	default:
		return "", false
	}
}

// writeRateLimitHeaders 写标准限流响应头，让客户端可自省预算。
func writeRateLimitHeaders(w http.ResponseWriter, d Decision) {
	if d.Remaining >= 0 {
		w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(d.Remaining))
	}
	if !d.ResetAt.IsZero() {
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(d.ResetAt.Unix(), 10))
	}
	if !d.Allowed && d.RetryAfter > 0 {
		secs := int(d.RetryAfter / time.Second)
		if secs < 1 {
			secs = 1
		}
		w.Header().Set("Retry-After", strconv.Itoa(secs))
	}
}

// PrincipalFromContext 从 context 读取 Principal。
//
// 键类型定义在 domain 包，auth 中间件写入的就是这个键，
// 因此这里无需 import auth 包即可读到鉴权结果（依赖只向内，见铁律 2）。
func PrincipalFromContext(ctx context.Context) (domain.Principal, bool) {
	return domain.PrincipalFrom(ctx)
}

// WithPrincipal 写入 Principal。仅供装配层与测试使用。
func WithPrincipal(ctx context.Context, p domain.Principal) context.Context {
	return domain.WithPrincipal(ctx, p)
}
