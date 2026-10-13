// Package cors 实现网关的跨域策略（三角之三）。
//
// CORS 三角分离（继承 Dify 的 console/service CORS 分离，扩展为三组）：
// console（控制台）、service（开放 API）、embed（网页嵌入）三个入口面
// 各有一套独立的 Policy，独立注册、独立求值、独立测试。
//
// 关键约束：本包不 import auth / ratelimit / routing 任何一包。
// "这个请求属于哪个入口面"由路由层写入 context 的 Surface 决定，
// 而 Surface 本身是 domain 层的纯值——所以 CORS 无需知道路由的存在。
package cors

import (
	"context"
	"net/http"
	"sort"
	"strconv"
	"strings"

	"github.com/linkai/gateway/internal/domain"
)

// WithSurface 把入口面写入 context。仅供路由层与测试使用。
func WithSurface(ctx context.Context, s domain.Surface) context.Context {
	return domain.WithSurface(ctx, s)
}

// SurfaceFrom 从 context 读取入口面。
func SurfaceFrom(ctx context.Context) (domain.Surface, bool) {
	return domain.SurfaceFrom(ctx)
}

// Policy 是一组入口面的跨域策略。零值不可用，必须经 NewPolicy 构造。
type Policy struct {
	// surface 本策略所属入口面。
	surface domain.Surface
	// allowedOrigins 允许的来源。含 "*" 表示任意（此时不得同时带 credentials）。
	allowedOrigins []string
	// allowAnyOrigin 是否为通配策略。
	allowAnyOrigin bool
	// allowedMethods 允许的方法。
	allowedMethods []string
	// allowedHeaders 允许的请求头。
	allowedHeaders []string
	// exposeHeaders 暴露给浏览器的响应头。
	exposeHeaders []string
	// allowCredentials 是否允许携带凭证。
	allowCredentials bool
	// maxAge 预检结果缓存秒数。
	maxAge int
}

// Option 是 Policy 的构造选项。
type Option func(*Policy)

// WithAllowedOrigins 设置允许的来源。传 "*" 表示通配。
//
// 来源按规范大小写敏感（scheme/host 部分由浏览器序列化后逐字比较），
// 因此只去首尾空格，不做大写转换。
func WithAllowedOrigins(origins ...string) Option {
	return func(p *Policy) {
		p.allowedOrigins = normalizeTrimmed(origins)
		p.allowAnyOrigin = contains(p.allowedOrigins, "*")
	}
}

// WithAllowedMethods 设置允许的方法。方法名大小写不敏感，统一转大写。
func WithAllowedMethods(methods ...string) Option {
	return func(p *Policy) {
		p.allowedMethods = normalizeUpper(methods)
	}
}

// WithAllowedHeaders 设置允许的请求头。头名大小写不敏感，统一转大写。
func WithAllowedHeaders(headers ...string) Option {
	return func(p *Policy) {
		p.allowedHeaders = normalizeUpper(headers)
	}
}

// WithExposeHeaders 设置暴露的响应头。头名大小写不敏感，统一转大写。
func WithExposeHeaders(headers ...string) Option {
	return func(p *Policy) {
		p.exposeHeaders = normalizeUpper(headers)
	}
}

// WithCredentials 允许携带凭证（Cookie / Authorization）。
func WithCredentials(enabled bool) Option {
	return func(p *Policy) { p.allowCredentials = enabled }
}

// WithMaxAge 设置预检缓存秒数。
func WithMaxAge(seconds int) Option {
	return func(p *Policy) {
		if seconds >= 0 {
			p.maxAge = seconds
		}
	}
}

// NewPolicy 创建某入口面的策略。
//
// 自校验两条硬规则（配置错必须启动期失败，不能留到运行时）：
//  1. 通配来源 "*" 不得与 credentials 同时开启——规范禁止，
//     且若放行会让任意站点带 Cookie 打我们的 API。
//  2. 空来源列表意味着该入口面完全不允许跨域，等价于关闭 CORS。
func NewPolicy(surface domain.Surface, opts ...Option) (*Policy, error) {
	p := &Policy{surface: surface}
	for _, opt := range opts {
		opt(p)
	}
	if p.allowAnyOrigin && p.allowCredentials {
		return nil, domain.ErrForbiddenTarget
	}
	return p, nil
}

// Surface 返回策略所属入口面。
func (p *Policy) Surface() domain.Surface { return p.surface }

// AllowsOrigin 判断来源是否被本策略允许。
//
// 通配策略对任何非空来源放行（但调用方需保证此时 credentials 为 false）；
// 精确策略只放行完全相等的来源。
func (p *Policy) AllowsOrigin(origin string) bool {
	if origin == "" {
		return false
	}
	if p.allowAnyOrigin {
		return true
	}
	return contains(p.allowedOrigins, origin)
}

// AllowsMethod 判断方法是否被允许。
func (p *Policy) AllowsMethod(method string) bool {
	return contains(p.allowedMethods, strings.ToUpper(method))
}

// AllowsHeader 判断请求头是否被允许（大小写不敏感）。
func (p *Policy) AllowsHeader(header string) bool {
	return containsFold(p.allowedHeaders, header)
}

// AllowsCredentials 返回是否允许携带凭证。
func (p *Policy) AllowsCredentials() bool { return p.allowCredentials }

// MaxAge 返回预检缓存秒数。
func (p *Policy) MaxAge() int { return p.maxAge }

// Apply 把策略写入响应头。调用前须先用 AllowsOrigin 判定通过。
func (p *Policy) Apply(w http.ResponseWriter, origin string) {
	h := w.Header()
	if p.allowAnyOrigin {
		h.Set("Access-Control-Allow-Origin", "*")
	} else {
		// 精确来源必须回显具体 origin，不能写 "*"。
		h.Set("Access-Control-Allow-Origin", origin)
		h.Add("Vary", "Origin")
	}
	if p.allowCredentials {
		h.Set("Access-Control-Allow-Credentials", "true")
	}
	if len(p.exposeHeaders) > 0 {
		h.Set("Access-Control-Expose-Headers", strings.Join(p.exposeHeaders, ", "))
	}
}

// ApplyPreflight 写预检响应头。
func (p *Policy) ApplyPreflight(w http.ResponseWriter, origin string) {
	p.Apply(w, origin)
	h := w.Header()
	if len(p.allowedMethods) > 0 {
		h.Set("Access-Control-Allow-Methods", strings.Join(p.allowedMethods, ", "))
	}
	if len(p.allowedHeaders) > 0 {
		h.Set("Access-Control-Allow-Headers", strings.Join(p.allowedHeaders, ", "))
	}
	if p.maxAge > 0 {
		h.Set("Access-Control-Max-Age", strconv.Itoa(p.maxAge))
	}
}

// Registry 是 CORS 策略注册表：每个入口面恰好一组策略，互不共享配置。
type Registry struct {
	policies map[domain.Surface]*Policy
}

// NewRegistry 创建空注册表。
func NewRegistry() *Registry {
	return &Registry{policies: make(map[domain.Surface]*Policy)}
}

// Register 注册一组策略。同一入口面重复注册返回 domain.ErrDuplicateSurface。
func (r *Registry) Register(p *Policy) error {
	if p == nil {
		return domain.ErrDuplicateSurface
	}
	if _, dup := r.policies[p.surface]; dup {
		return domain.ErrDuplicateSurface
	}
	r.policies[p.surface] = p
	return nil
}

// Lookup 取某入口面的策略。
func (r *Registry) Lookup(s domain.Surface) (*Policy, bool) {
	p, ok := r.policies[s]
	return p, ok
}

// Surfaces 返回已注册入口面，按字典序保证输出稳定（便于测试断言）。
func (r *Registry) Surfaces() []domain.Surface {
	out := make([]domain.Surface, 0, len(r.policies))
	for s := range r.policies {
		out = append(out, s)
	}
	sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
	return out
}

// Middleware 是 CORS 中间件。
type Middleware struct {
	registry *Registry
}

// NewMiddleware 组装 CORS 中间件。
func NewMiddleware(reg *Registry) *Middleware {
	return &Middleware{registry: reg}
}

// Handle 处理跨域。
//
// 分工：本中间件只处理"能不能跨域"。它绝不因为跨域被拒就拒绝同源请求，
// 也不因为跨域被允许就放行鉴权——鉴权由 auth 中间件独立负责。
func (m *Middleware) Handle(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		surface, ok := SurfaceFrom(r.Context())
		if !ok {
			// 没有入口面 = 请求没经过路由，拒绝一切跨域声明。
			// 这不是 403：跨域失败按规范由浏览器拦截，服务端仍应正常响应。
			next.ServeHTTP(w, r)
			return
		}

		policy, ok := m.registry.Lookup(surface)
		if !ok {
			// 该入口面未配置策略 = 不允许跨域。
			next.ServeHTTP(w, r)
			return
		}

		origin := r.Header.Get("Origin")
		if origin == "" || !policy.AllowsOrigin(origin) {
			// 来源不允许：不写任何 CORS 头。浏览器会自行拦截，
			// 服务端继续正常处理——这是 CORS 规范推荐的行为。
			next.ServeHTTP(w, r)
			return
		}

		if r.Method == http.MethodOptions && r.Header.Get("Access-Control-Request-Method") != "" {
			if !policy.AllowsMethod(r.Header.Get("Access-Control-Request-Method")) {
				next.ServeHTTP(w, r)
				return
			}
			if reqHeaders := r.Header.Get("Access-Control-Request-Headers"); reqHeaders != "" {
				for _, h := range strings.Split(reqHeaders, ",") {
					if !policy.AllowsHeader(strings.TrimSpace(h)) {
						next.ServeHTTP(w, r)
						return
					}
				}
			}
			policy.ApplyPreflight(w, origin)
			w.WriteHeader(http.StatusNoContent)
			return
		}

		policy.Apply(w, origin)
		next.ServeHTTP(w, r)
	})
}

// normalizeTrimmed 去首尾空格并丢弃空项，保留原大小写。
func normalizeTrimmed(in []string) []string {
	out := make([]string, 0, len(in))
	for _, v := range in {
		v = strings.TrimSpace(v)
		if v == "" {
			continue
		}
		out = append(out, v)
	}
	return out
}

// normalizeUpper 去首尾空格并统一转大写，用于方法名与头名。
func normalizeUpper(in []string) []string {
	out := make([]string, 0, len(in))
	for _, v := range normalizeTrimmed(in) {
		out = append(out, strings.ToUpper(v))
	}
	return out
}

// contains 判断是否包含（区分大小写）。
func contains(haystack []string, needle string) bool {
	for _, v := range haystack {
		if v == needle {
			return true
		}
	}
	return false
}

// containsFold 判断是否包含（忽略大小写）。输入需已转大写。
func containsFold(haystack []string, needle string) bool {
	return contains(haystack, strings.ToUpper(strings.TrimSpace(needle)))
}
