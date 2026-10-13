// Package domain 定义网关的领域值对象。
//
// 铁律 2（四层架构）：本包是最内层，不依赖任何框架——不 import net/http、
// chi、JWT、CORS 等。只允许标准库中的纯数据结构与 error。
package domain

import (
	"errors"
	"time"
)

// CredentialKind 标识凭证类型。不同类型走不同的认证适配器（铁律 4：注册机制）。
type CredentialKind string

const (
	// CredentialJWT 控制台/开放 API 的 JWT Bearer 凭证。
	CredentialJWT CredentialKind = "jwt"
	// CredentialAPIKey 服务端到服务端的 API Key 凭证。
	CredentialAPIKey CredentialKind = "apikey"
)

// Surface 标识请求入口面。CORS 三组策略按此维度完全隔离，
// 防止 console / service / embed 的跨域策略互相串染。
type Surface string

const (
	// SurfaceConsole 控制台 API（web-console 访问）。
	SurfaceConsole Surface = "console"
	// SurfaceService 开放 API（sdk / 服务端调用）。
	SurfaceService Surface = "service"
	// SurfaceEmbed 网页嵌入（第三方站点 iframe）。
	SurfaceEmbed Surface = "embed"
)

// AllSurfaces 返回全部入口面，顺序稳定，用于遍历与测试断言。
func AllSurfaces() []Surface {
	return []Surface{SurfaceConsole, SurfaceService, SurfaceEmbed}
}

// Principal 是通过鉴权后的调用方身份，是后续所有横切机制的入参。
//
// 铁律 6（多租户）：TenantID 为空表示未绑定租户，鉴权层必须拒绝该状态，
// 下游（限流/路由/后端服务）只信任鉴权层写入的 Principal。
type Principal struct {
	// TenantID 租户标识，所有下游数据操作必须携带。
	TenantID string
	// SubjectID 调用方主体标识（用户 ID 或应用 ID）。
	SubjectID string
	// Kind 凭证类型。
	Kind CredentialKind
	// Scopes 权限范围，路由层可按需校验。
	Scopes []string
	// ExpiresAt 凭证过期时刻，零值表示不过期（如 API Key）。
	ExpiresAt time.Time
}

// IsExpired 判断凭证是否在给定时刻已过期。
func (p Principal) IsExpired(now time.Time) bool {
	if p.ExpiresAt.IsZero() {
		return false
	}
	return !now.Before(p.ExpiresAt)
}

// HasScope 判断是否持有指定 scope。
func (p Principal) HasScope(scope string) bool {
	for _, s := range p.Scopes {
		if s == scope {
			return true
		}
	}
	return false
}

// 鉴权与限流的领域错误。用哨兵 error 而非字符串，便于 errors.Is 断言。
var (
	// ErrMissingCredential 未携带任何凭证。
	ErrMissingCredential = errors.New("domain: missing credential")
	// ErrInvalidCredential 凭证格式非法或签名校验失败。
	ErrInvalidCredential = errors.New("domain: invalid credential")
	// ErrExpiredCredential 凭证已过期。
	ErrExpiredCredential = errors.New("domain: credential expired")
	// ErrRevokedCredential 凭证已被吊销。
	ErrRevokedCredential = errors.New("domain: credential revoked")
	// ErrTenantMismatch 凭证与目标租户不一致。
	ErrTenantMismatch = errors.New("domain: credential tenant mismatch")
	// ErrMissingTenant Principal 未绑定租户，违反铁律 6。
	ErrMissingTenant = errors.New("domain: principal has no tenant")
)

// 限流领域错误。
var (
	// ErrRateLimited 触发限流。
	ErrRateLimited = errors.New("domain: rate limited")
	// ErrRateLimitMisconfigured 限流策略配置非法。
	ErrRateLimitMisconfigured = errors.New("domain: rate limit misconfigured")
)

// SSRF 领域错误。
var (
	// ErrForbiddenTarget 出站目标被安全基线拒绝（内网/保留地址）。
	ErrForbiddenTarget = errors.New("domain: outbound target forbidden")
	// ErrMalformedTarget 出站目标 URL 非法。
	ErrMalformedTarget = errors.New("domain: outbound target malformed")
)

// 路由领域错误。
var (
	// ErrNoRoute 没有任何路由匹配。
	ErrNoRoute = errors.New("domain: no matching route")
	// ErrBackendUnreachable 后端不可达。
	ErrBackendUnreachable = errors.New("domain: backend unreachable")
	// ErrDuplicateRoute 路由重复注册。
	ErrDuplicateRoute = errors.New("domain: duplicate route")
)

// CORS 领域错误。
var (
	// ErrDuplicateSurface 同一入口面重复注册 CORS 策略。
	ErrDuplicateSurface = errors.New("domain: duplicate cors surface")
	// ErrUnknownSurface 请求落在未配置策略的入口面上。
	ErrUnknownSurface = errors.New("domain: unknown cors surface")
)
