// Package routing 实现网关的路由与转发（三角之四）。
//
// 职责边界：本包只回答"这个请求该去哪个后端"。它不校验凭证、不判限流、不管 CORS，
// 只做三件事：按注册表匹配路由、注入多租户上下文头、反向代理。
//
// 铁律 4（注册机制）：后端服务一律走 Upstream 注册表，
// 新增一个后端 = 注册一条 Upstream + 一条 Route，不改本包任何代码。
package routing

import (
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// 注入下游的租户头（铁律 6：tenant_id 从网关注入，全链路透传）。
// 下游服务只信任来自网关的该头，不接受客户端直传。
const (
	// HeaderTenantID 租户头，与鉴权层同名。
	HeaderTenantID = "X-Tenant-Id"
	// HeaderSubjectID 调用方主体头。
	HeaderSubjectID = "X-Subject-Id"
	// HeaderSurface 入口面头，供下游做差异化响应。
	HeaderSurface = "X-Gateway-Surface"
	// HeaderTraceID 链路追踪 ID，贯穿网关→服务→插件/模型。
	HeaderTraceID = "X-Trace-Id"
	// HeaderTraceParent 上游 traceparent，供 OTel 上下文延续。
	HeaderTraceParent = "traceparent"
)

// Upstream 是一个后端服务。
type Upstream struct {
	// Name 服务标识，作为路由表的引用键。
	Name string
	// Target 形如 "http://127.0.0.1:8001" 的上游地址。
	Target string
	// Surface 该服务归属的入口面，决定适用哪一组 CORS 策略。
	Surface domain.Surface
	// RequiredScopes 访问该服务所需的最小 scope 集合，任一缺失即 403。
	RequiredScopes []string
}

// Route 是一条路由规则。
type Route struct {
	// Method HTTP 方法，大写。
	Method string
	// PathPrefix 路径前缀。
	PathPrefix string
	// Upstream 目标服务名。
	Upstream string
}

// Table 是路由表 + 上游注册表。
//
// 启动期一次性构建，运行期只读——因此 ServeHTTP 可以无锁并发访问。
type Table struct {
	upstreams map[string]Upstream
	routes    []Route
}

// NewTable 创建空路由表。
func NewTable() *Table {
	return &Table{upstreams: make(map[string]Upstream)}
}

// RegisterUpstream 注册后端服务。重复注册同名返回 domain.ErrDuplicateRoute。
func (t *Table) RegisterUpstream(u Upstream) error {
	if u.Name == "" || u.Target == "" {
		return domain.ErrNoRoute
	}
	if _, dup := t.upstreams[u.Name]; dup {
		return domain.ErrDuplicateRoute
	}
	t.upstreams[u.Name] = u
	return nil
}

// RegisterRoute 注册路由。上游必须已注册，否则返回 domain.ErrNoRoute。
func (t *Table) RegisterRoute(r Route) error {
	if _, ok := t.upstreams[r.Upstream]; !ok {
		return domain.ErrNoRoute
	}
	r.Method = strings.ToUpper(strings.TrimSpace(r.Method))
	r.PathPrefix = strings.TrimSuffix(strings.TrimSpace(r.PathPrefix), "/")
	if r.Method == "" || r.PathPrefix == "" {
		return domain.ErrNoRoute
	}
	for _, existing := range t.routes {
		if existing.Method == r.Method && existing.PathPrefix == r.PathPrefix {
			return domain.ErrDuplicateRoute
		}
	}
	t.routes = append(t.routes, r)
	return nil
}

// Lookup 按方法与路径匹配路由。返回最长前缀匹配，路径无关的顺序稳定。
func (t *Table) Lookup(method, path string) (Upstream, Route, bool) {
	method = strings.ToUpper(method)
	var (
		bestUpstream Upstream
		bestRoute    Route
		found        bool
		bestLen      int
	)
	for _, r := range t.routes {
		if r.Method != method {
			continue
		}
		if !strings.HasPrefix(path, r.PathPrefix) {
			continue
		}
		// 最长前缀优先：/service/v1/chat 应胜过 /service
		if len(r.PathPrefix) > bestLen {
			u, ok := t.upstreams[r.Upstream]
			if !ok {
				continue
			}
			bestUpstream, bestRoute, bestLen, found = u, r, len(r.PathPrefix), true
		}
	}
	return bestUpstream, bestRoute, found
}

// Upstreams 返回已注册上游名，按字典序保证输出稳定。
func (t *Table) Upstreams() []string {
	out := make([]string, 0, len(t.upstreams))
	for name := range t.upstreams {
		out = append(out, name)
	}
	sortStrings(out)
	return out
}

// NewTraceID 生成一个新的链路追踪 ID。
//
// 用 crypto/rand 而非 math/rand：trace ID 会出现在日志与下游响应里，
// 可预测的 ID 会让攻击者能关联/伪造他人请求。
func NewTraceID() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err != nil {
		// crypto/rand 失败属系统级异常，退化为时间戳保证链路不中断。
		return "ts-" + strconv.FormatInt(time.Now().UnixNano(), 16)
	}
	return hex.EncodeToString(buf[:])
}

// sortStrings 是极简字典序排序，避免为一个函数引 sort 包。
func sortStrings(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j] < s[j-1]; j-- {
			s[j], s[j-1] = s[j-1], s[j]
		}
	}
}

// Proxy 是反向代理器接口。骨架阶段由 infra/proxy 提供 net/http 实现，
// 此处只依赖接口，便于测试时注入假实现。
type Proxy interface {
	// Serve 转发请求到 target，并按需改写路径。
	Serve(w http.ResponseWriter, r *http.Request, u Upstream)
}

// Middleware 是路由中间件。
type Middleware struct {
	table *Table
	proxy Proxy
}

// NewMiddleware 组装路由中间件。
func NewMiddleware(table *Table, proxy Proxy) *Middleware {
	return &Middleware{table: table, proxy: proxy}
}

// Handle 匹配路由并转发。
func (m *Middleware) Handle(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		u, _, ok := m.table.Lookup(r.Method, r.URL.Path)
		if !ok {
			writeRoutingError(w, r, domain.ErrNoRoute)
			return
		}

		p, hasPrincipal := domain.PrincipalFrom(r.Context())
		if !hasPrincipal || p.TenantID == "" {
			// 没有租户上下文的请求绝不允许出网（铁律 6）。
			writeRoutingError(w, r, domain.ErrMissingTenant)
			return
		}

		// scope 校验：与鉴权/限流完全独立，只在路由层做资源级授权。
		for _, need := range u.RequiredScopes {
			if !p.HasScope(need) {
				writeRoutingError(w, r, domain.ErrForbiddenTarget)
				return
			}
		}

		// 注入租户上下文并标记入口面，供 CORS 与下游服务消费。
		ctx := domain.WithSurface(r.Context(), u.Surface)
		r = r.WithContext(ctx)
		r.Header.Set(HeaderTenantID, p.TenantID)
		r.Header.Set(HeaderSubjectID, p.SubjectID)
		r.Header.Set(HeaderSurface, string(u.Surface))
		if r.Header.Get(HeaderTraceID) == "" {
			r.Header.Set(HeaderTraceID, NewTraceID())
		}

		m.proxy.Serve(w, r, u)
	})
}

// HandleUnmatched 是无匹配路由时的兜底处理（供 chi 的 NotFound 使用）。
func (m *Middleware) HandleUnmatched(w http.ResponseWriter, r *http.Request) {
	writeRoutingError(w, r, domain.ErrNoRoute)
}

// writeRoutingError 把领域错误映射为 HTTP 状态码。
func writeRoutingError(w http.ResponseWriter, r *http.Request, err error) {
	status := http.StatusNotFound
	switch err {
	case domain.ErrMissingTenant:
		status = http.StatusInternalServerError
	case domain.ErrForbiddenTarget:
		status = http.StatusForbidden
	case domain.ErrBackendUnreachable:
		status = http.StatusBadGateway
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(`{"error":"` + errTag(status) + `"}`))
}

// errTag 返回稳定的错误标签，便于前端契约断言。
func errTag(status int) string {
	switch status {
	case http.StatusNotFound:
		return "not_found"
	case http.StatusForbidden:
		return "forbidden"
	case http.StatusBadGateway:
		return "bad_gateway"
	default:
		return "internal_error"
	}
}
