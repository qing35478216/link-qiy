// Package routing 实现网关的路由与转发（三角之四）。
//
// 职责边界：本包只回答"这个请求该去哪个后端"。它不校验凭证、不判限流、不管 CORS，
// 只做三件事：按注册表匹配路由、注入多租户上下文头、反向代理。
//
// 铁律 4（注册机制）：后端服务一律走 Upstream 注册表，
// 新增一个后端 = 注册一条 Upstream + 一条 Route，不改本包任何代码。
package routing

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// 注入下游的身份头（铁律 6：tenant_id 从网关注入，全链路透传）。
//
// 安全要求（T-005 对齐）：下游服务只信任来自网关的这些头，不接受客户端直传。
// 因此网关注入前**必须先剥离**客户端传入的同名头——否则用户可以
// 携带 X-Tenant-Id / X-User-Id 直接伪造身份，造成跨租户串账。
const (
	// HeaderTenantID 租户头，与鉴权层同名，契约 schemas/common.yaml 有定义。
	HeaderTenantID = "X-Tenant-Id"
	// HeaderUserID 调用方用户头。命名与下游服务（model-proxy）约定一致，
	// 不要改成 X-Subject-Id 之类——名字不一致会导致下游读到空值，
	// 更糟的是客户端自带的 X-Subject-Id 会静默穿透到下游。
	HeaderUserID = "X-User-Id"
	// HeaderSurface 入口面头，供下游做差异化响应。
	HeaderSurface = "X-Gateway-Surface"
	// HeaderTraceID 链路追踪 ID，贯穿网关→服务→插件/模型。
	HeaderTraceID = "X-Trace-Id"
	// HeaderTraceParent 上游 traceparent，供 OTel 上下文延续。
	HeaderTraceParent = "traceparent"
)

// identityHeaders 是**网关注入的调用方身份**头清单。
//
// 定义域要说准：这个清单只管"网关注入的身份"，不管"转发链信息"。
// 承载客户端 IP 的头（X-Real-IP 等）语义上属于后者，
// 由 infra/proxy 在 SetXForwarded() 处处理——
// 把它们塞进这里会混淆语义，让人误以为 identityHeaders 是"所有该剥离的头"。
//
// 用途二：这是"这些头归网关管"的权责声明，新增下游服务时照此扩充。
var identityHeaders = []string{
	HeaderTenantID,
	HeaderUserID,
	HeaderSurface,
	HeaderTraceID,
	HeaderTraceParent,
}

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

// LookupAnyMethod 按路径匹配路由，忽略 HTTP 方法。
//
// 专供 OPTIONS 预检使用：预检请求的实际方法写在
// Access-Control-Request-Method 头里，方法本身恒为 OPTIONS，
// 若按方法匹配会全部落空，导致跨域预检一律 404。
func (t *Table) LookupAnyMethod(path string) (Upstream, Route, bool) {
	var (
		bestUpstream Upstream
		bestRoute    Route
		found        bool
		bestLen      int
	)
	for _, r := range t.routes {
		if !strings.HasPrefix(path, r.PathPrefix) {
			continue
		}
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

// clientCredentialHeaders 是客户端凭证载体头。
//
// 为什么要剥离（主理人/qa-reviewer 指出，实测确认原样透传）：
// 网关已完成鉴权与配额裁决，客户端再带一份凭证到下游，会形成
// **双重鉴权入口**——下游若自行校验，看到的是客户端原始凭证而非
// 网关的裁决结论，可能在网关已封禁/限流后仍按自己的判断放行。
//
// 剥离后下游只认网关注入的身份头（X-User-Id / X-Tenant-Id），
// 网关成为唯一鉴权决策点。Cookie 同理：它承载浏览器会话，
// 而网关不是面向浏览器的会话入口。
var clientCredentialHeaders = []string{
	"Authorization",
	"Cookie",
	"Proxy-Authorization",
}

// legacyIdentityHeaders 是历史上用过、现已废弃的身份头名。
//
// 由来：T-005 对齐时本网关曾用 X-Subject-Id，而下游 model-proxy
// 读 X-User-Id，命名不一致导致真实身份断流、客户端伪造值畅通。
// 统一为 X-User-Id 后 X-Subject-Id 成为废弃名。
//
// 为什么仍要剥离：客户端可能仍在发送旧名（灰度期、缓存的 SDK、
// 第三方集成）。若不剥离，它会静默穿透到下游，造成"看起来有身份、
// 实际来源不明"的排查噩梦。**废弃 ≠ 不管**，这是安全头与普通 API 的差别。
var legacyIdentityHeaders = []string{
	"X-Subject-Id",
}

// sanitizeIdentityHeaders 剥离客户端传入的身份头与凭证头。
//
// 网关是唯一可信的身份来源，因此下游服务收到的这些头必须 100% 来自网关。
// 不做剥离的后果（实测）：客户端携带 X-User-Id: victim-9999 直连
// 网关，该值会原样透传到 model-proxy，而后者信任它作为调用方身份。
func sanitizeIdentityHeaders(r *http.Request) {
	for _, h := range identityHeaders {
		r.Header.Del(h)
	}
	for _, h := range legacyIdentityHeaders {
		r.Header.Del(h)
	}
	for _, h := range clientCredentialHeaders {
		r.Header.Del(h)
	}
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

// Resolver 只做"匹配路由 + 标记入口面"，不做任何鉴权判断。
//
// 拆出独立阶段的原因：入口面必须在鉴权之前就能确定——
// OPTIONS 预检不携带凭证，若 CORS 排在鉴权之后，
// 所有跨域预检都会 401，浏览器直接判定跨域失败（实测已验证）。
// 所以装配链是：Resolve → CORS → 鉴权 → 限流 → Forward。
type Resolver struct {
	table *Table
}

// NewResolver 组装路由解析器。
func NewResolver(table *Table) *Resolver { return &Resolver{table: table} }

// matchedKey 是匹配结果在 context 中的键类型。
// 定义在本包内——只有 routing 自己写自己读，无需放到 domain。
type matchedKey struct{}

// MatchedRoute 是一次匹配的结果。
type MatchedRoute struct {
	Upstream Upstream
	Route    Route
}

// MatchedFrom 从 context 读取匹配结果。
func MatchedFrom(ctx context.Context) (MatchedRoute, bool) {
	m, ok := ctx.Value(matchedKey{}).(MatchedRoute)
	return m, ok
}

// Handle 匹配路由，把入口面与上游写入 context，然后放行。
// 无匹配路由直接 404——后续所有机制都不必再跑。
func (res *Resolver) Handle(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		u, route, ok := res.lookup(r)
		if !ok {
			HandleUnmatched(w, r)
			return
		}
		ctx := context.WithValue(r.Context(), matchedKey{}, MatchedRoute{Upstream: u, Route: route})
		// 入口面写入最内层的 context 键，供 CORS 中间件读取——
		// CORS 因此无需 import 本包，两者在装配层解耦。
		ctx = domain.WithSurface(ctx, u.Surface)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// lookup 选择匹配方式：CORS 预检按路径匹配，其余按方法+路径匹配。
func (res *Resolver) lookup(r *http.Request) (Upstream, Route, bool) {
	if isPreflight(r) {
		return res.table.LookupAnyMethod(r.URL.Path)
	}
	return res.table.Lookup(r.Method, r.URL.Path)
}

// isPreflight 判断是否为 CORS 预检请求。
func isPreflight(r *http.Request) bool {
	return r.Method == http.MethodOptions && r.Header.Get("Access-Control-Request-Method") != ""
}

// Middleware 是转发阶段：鉴权已在链路中完成，这里做租户与 scope 的出口校验后转发。
type Middleware struct {
	proxy Proxy
}

// NewForwarder 组装转发中间件。
func NewMiddleware(proxy Proxy) *Middleware {
	return &Middleware{proxy: proxy}
}

// Handle 校验租户上下文与 scope，然后转发到上游。
func (m *Middleware) Handle(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		matched, ok := MatchedFrom(r.Context())
		if !ok {
			writeRoutingError(w, r, domain.ErrNoRoute)
			return
		}
		u := matched.Upstream

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

		// 先剥离客户端伪造的身份头，再注入可信值。
		//
		// 顺序不能反：若先注入再剥离会把可信值也删掉；
		// 若只注入不剥离，客户端自带的同名头会在 Set 之外的其他
		// 头（如 X-User-Id）穿透到下游，造成身份伪造与跨租户串账。
		sanitizeIdentityHeaders(r)

		// 注入租户上下文，供下游服务消费（铁律 6）。
		r.Header.Set(HeaderTenantID, p.TenantID)
		if p.SubjectID != "" {
			r.Header.Set(HeaderUserID, p.SubjectID)
		}
		r.Header.Set(HeaderSurface, string(u.Surface))
		// trace_id 一律由网关生成：客户端提供的值不可信，
		// 放任其穿透等于允许伪造审计与计费对账的关联键。
		r.Header.Set(HeaderTraceID, NewTraceID())

		m.proxy.Serve(w, r, u)
	})
}

// HandleUnmatched 是无匹配路由时的兜底处理（404）。
func HandleUnmatched(w http.ResponseWriter, r *http.Request) {
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
