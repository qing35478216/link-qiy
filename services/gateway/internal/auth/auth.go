// Package auth 实现网关的鉴权横切机制（三角之一）。
//
// 职责边界：本包只回答"这是谁"。它不关心限流阈值、路由目标、CORS 策略，
// 也不写任何业务/AI 逻辑。三者之间无 import 依赖，可各自单独测试。
package auth

import (
	"context"
	"net/http"
	"strings"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// 约定头。集中定义避免各适配器散落硬编码字符串。
const (
	// HeaderAuthorization 标准认证头。
	HeaderAuthorization = "Authorization"
	// HeaderAPIKey 服务端到服务端 API Key 头。
	//nolint:gosec // G101：这是 HTTP 头名称，不是凭据本身
	HeaderAPIKey = "X-API-Key"
	// HeaderTenantID 客户端声明的目标租户，网关必须与凭证租户比对（铁律 6）。
	HeaderTenantID = "X-Tenant-Id"
	// headerSchemeBearer Bearer 前缀。
	headerSchemeBearer = "bearer "
)

// FromContext 取出鉴权写入的 Principal。
//
// 键类型定义在 domain 包（domain/context.go），与 ratelimit 共用，
// 这样鉴权写入、限流读取能命中同一个值，两个包之间仍无 import 依赖。
func FromContext(ctx context.Context) (domain.Principal, bool) {
	return domain.PrincipalFrom(ctx)
}

// WithPrincipal 把 Principal 写入 context。仅供中间件与测试使用。
func WithPrincipal(ctx context.Context, p domain.Principal) context.Context {
	return domain.WithPrincipal(ctx, p)
}

// Authenticator 是认证适配器接口（铁律 4：新认证方式 = 新适配器 + 注册，不改内核）。
type Authenticator interface {
	// Kind 声明本适配器处理的凭证类型，注册表按此分派。
	Kind() domain.CredentialKind
	// Authenticate 从请求中提取并校验凭证，成功返回 Principal。
	// 失败必须返回 domain 包中的哨兵 error，便于上层归类 HTTP 状态码。
	Authenticate(r *http.Request) (domain.Principal, error)
}

// Registry 是认证适配器注册表。重复注册同一 Kind 会 panic——
// 网关是启动期装配的进程，重复注册意味着编程错误，必须在启动时暴露。
type Registry struct {
	adapters map[domain.CredentialKind]Authenticator
}

// NewRegistry 创建空注册表。
func NewRegistry() *Registry {
	return &Registry{adapters: make(map[domain.CredentialKind]Authenticator)}
}

// Register 注册一个认证适配器。同一 Kind 重复注册将 panic。
func (r *Registry) Register(a Authenticator) {
	if a == nil {
		panic("auth: Register(nil adapter)")
	}
	kind := a.Kind()
	if _, dup := r.adapters[kind]; dup {
		panic("auth: duplicate authenticator for kind " + string(kind))
	}
	r.adapters[kind] = a
}

// Lookup 按凭证类型取适配器。
func (r *Registry) Lookup(k domain.CredentialKind) (Authenticator, bool) {
	a, ok := r.adapters[k]
	return a, ok
}

// Kinds 返回已注册的凭证类型列表，供启动日志与测试断言使用。
func (r *Registry) Kinds() []domain.CredentialKind {
	out := make([]domain.CredentialKind, 0, len(r.adapters))
	for k := range r.adapters {
		out = append(out, k)
	}
	return out
}

// Middleware 是鉴权中间件。它只依赖 Registry 与少量策略回调，
// 不依赖限流/路由/CORS 任何一包——这是"三角分离"的硬约束。
type Middleware struct {
	registry *Registry
	// now 可注入，便于测试过期场景；nil 表示 time.Now。
	now func() time.Time
}

// NewMiddleware 组装鉴权中间件。
func NewMiddleware(reg *Registry, now func() time.Time) *Middleware {
	if now == nil {
		now = time.Now
	}
	return &Middleware{registry: reg, now: now}
}

// Handle 执行鉴权。成功则把 Principal 注入 context 并放行；
// 失败则写回状态码并终止链路。
func (m *Middleware) Handle(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p, err := m.Authenticate(r)
		if err != nil {
			writeAuthError(w, err)
			return
		}
		next.ServeHTTP(w, r.WithContext(WithPrincipal(r.Context(), p)))
	})
}

// Authenticate 是可独立测试的鉴权核心，不触碰 http.ResponseWriter。
func (m *Middleware) Authenticate(r *http.Request) (domain.Principal, error) {
	kind, ok := detectKind(r)
	if !ok {
		return domain.Principal{}, domain.ErrMissingCredential
	}

	adapter, ok := m.registry.Lookup(kind)
	if !ok {
		// 带了凭证但没有对应适配器，按非法凭证处理，不泄露内部注册状态。
		return domain.Principal{}, domain.ErrInvalidCredential
	}

	p, err := adapter.Authenticate(r)
	if err != nil {
		return domain.Principal{}, err
	}

	// 铁律 6：租户必须存在，且与客户端声明一致。裸租户请求一律拒绝。
	if p.TenantID == "" {
		return domain.Principal{}, domain.ErrMissingTenant
	}
	if declared := strings.TrimSpace(r.Header.Get(HeaderTenantID)); declared != "" && declared != p.TenantID {
		return domain.Principal{}, domain.ErrTenantMismatch
	}

	// 过期复核：适配器可能有自己的时钟，这里用网关统一时钟兜底。
	if p.IsExpired(m.now()) {
		return domain.Principal{}, domain.ErrExpiredCredential
	}
	return p, nil
}

// detectKind 依据请求头判断凭证类型。故意做成纯函数，便于覆盖各类缺失组合。
func detectKind(r *http.Request) (domain.CredentialKind, bool) {
	if strings.TrimSpace(r.Header.Get(HeaderAPIKey)) != "" {
		return domain.CredentialAPIKey, true
	}
	authz := r.Header.Get(HeaderAuthorization)
	if len(authz) > len(headerSchemeBearer) &&
		strings.EqualFold(authz[:len(headerSchemeBearer)], headerSchemeBearer) &&
		strings.TrimSpace(authz[len(headerSchemeBearer):]) != "" {
		return domain.CredentialJWT, true
	}
	return "", false
}

// writeAuthError 把领域错误映射为 HTTP 状态码。
// 401 用于凭证本身有问题，403 用于身份有效但无权访问该租户。
func writeAuthError(w http.ResponseWriter, err error) {
	status := http.StatusUnauthorized
	if err == domain.ErrTenantMismatch {
		status = http.StatusForbidden
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	// 响应体不区分"签名错/过期/吊销"，避免凭证探测 oracle。
	_, _ = w.Write([]byte(`{"error":"unauthorized"}`))
}
