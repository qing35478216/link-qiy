// Package jwt 实现 JWT 认证适配器。
//
// 它是 auth.Authenticator 接口的一个实现（铁律 4：适配器 + 注册表）。
// 本包依赖 auth 接口与 domain 值对象，不反向依赖网关内核。
package jwt

import (
	"crypto/subtle"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"github.com/linkai/gateway/internal/auth"
	"github.com/linkai/gateway/internal/domain"
)

// 固定 claim 名，与 platform 服务的签发约定对齐（契约在 packages/contracts，本包只消费）。
const (
	// ClaimTenantID 租户 claim。
	ClaimTenantID = "tenant_id"
	// ClaimSubjectID 主体 claim。
	ClaimSubjectID = "sub"
	// ClaimScopes 权限范围 claim。
	ClaimScopes = "scopes"
)

// Authenticator 用对称密钥校验 JWT。
type Authenticator struct {
	secret []byte
	// issuer 校验签发方，空串表示不校验。
	issuer string
	// leeway 允许的时钟偏移。
	leeway time.Duration
	// now 可注入，便于测试过期用例。
	now func() time.Time
}

// Config 是 JWT 适配器配置。
type Config struct {
	Secret []byte
	Issuer string
	Leeway time.Duration
	Now    func() time.Time
}

// New 创建 JWT 认证适配器。密钥为空直接 panic——空密钥会让所有令牌可伪造，
// 属于必须在启动期暴露的安全配置错误。
func New(cfg Config) *Authenticator {
	if len(cfg.Secret) == 0 {
		panic("jwt: empty signing secret")
	}
	now := cfg.Now
	if now == nil {
		now = time.Now
	}
	return &Authenticator{
		secret:  cfg.Secret,
		issuer:  cfg.Issuer,
		leeway:  cfg.Leeway,
		now:     now,
	}
}

// Kind 实现 auth.Authenticator。
func (a *Authenticator) Kind() domain.CredentialKind { return domain.CredentialJWT }

// Authenticate 校验 Bearer 令牌。
//
// 三类失败被刻意区分在内部，但对外统一映射到 domain 哨兵 error：
//   - 篡改（签名不匹配 / 结构非法）→ ErrInvalidCredential
//   - 过期（含 nbf 未生效）→ ErrExpiredCredential
//   - 签发方不符 → ErrInvalidCredential
func (a *Authenticator) Authenticate(r *http.Request) (domain.Principal, error) {
	raw, ok := bearerToken(r.Header.Get(auth.HeaderAuthorization))
	if !ok {
		return domain.Principal{}, domain.ErrMissingCredential
	}

	// 用 MapClaims 一次拿到注册 claim 与自定义 claim，避免两次解析。
	opts := []jwt.ParserOption{
		jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}),
		jwt.WithExpirationRequired(),
		jwt.WithTimeFunc(a.now),
		jwt.WithLeeway(a.leeway),
	}
	if a.issuer != "" {
		opts = append(opts, jwt.WithIssuer(a.issuer))
	}

	claims := jwt.MapClaims{}
	token, err := jwt.NewParser(opts...).ParseWithClaims(raw, claims,
		func(t *jwt.Token) (any, error) {
			// 二次确认 alg，避免 alg=none 或算法混淆攻击。
			if t.Method != jwt.SigningMethodHS256 {
				return nil, errors.New("jwt: unexpected signing method")
			}
			return a.secret, nil
		})
	if err != nil {
		return domain.Principal{}, classifyParseError(err)
	}
	if !token.Valid {
		return domain.Principal{}, domain.ErrInvalidCredential
	}

	exp, _ := claims.GetExpirationTime()
	subject, _ := claims.GetSubject()
	p := domain.Principal{
		Kind:      domain.CredentialJWT,
		SubjectID: subject,
	}
	if exp != nil {
		p.ExpiresAt = exp.Time
	}
	if v, ok := claims[ClaimTenantID].(string); ok {
		p.TenantID = v
	}
	p.Scopes = readScopes(claims[ClaimScopes])

	// 缺租户的令牌不在此报错：交由 auth 中间件统一归为 ErrMissingTenant，
	// 保证"无租户"在全网关只有一种失败语义（铁律 6）。
	return p, nil
}

// classifyParseError 把 jwt 库的错误翻译为领域错误。
func classifyParseError(err error) error {
	switch {
	case errors.Is(err, jwt.ErrTokenExpired),
		errors.Is(err, jwt.ErrTokenNotValidYet):
		return domain.ErrExpiredCredential
	case errors.Is(err, jwt.ErrTokenSignatureInvalid),
		errors.Is(err, jwt.ErrTokenMalformed),
		errors.Is(err, jwt.ErrTokenUnverifiable),
		errors.Is(err, jwt.ErrTokenRequiredClaimMissing),
		errors.Is(err, jwt.ErrTokenInvalidClaims),
		errors.Is(err, jwt.ErrTokenInvalidAudience),
		errors.Is(err, jwt.ErrTokenInvalidIssuer),
		errors.Is(err, jwt.ErrTokenInvalidSubject),
		errors.Is(err, jwt.ErrTokenNotValidYet),
		errors.Is(err, jwt.ErrTokenUsedBeforeIssued):
		return domain.ErrInvalidCredential
	default:
		return domain.ErrInvalidCredential
	}
}

// readScopes 兼容字符串与字符串数组两种 scope 编码。
func readScopes(v any) []string {
	switch t := v.(type) {
	case string:
		if t == "" {
			return nil
		}
		return strings.Split(t, " ")
	case []any:
		out := make([]string, 0, len(t))
		for _, item := range t {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out
	case []string:
		return t
	default:
		return nil
	}
}

// bearerToken 提取 Bearer 令牌。空令牌返回 false，避免把空串当有效凭证。
func bearerToken(header string) (string, bool) {
	const prefix = "bearer "
	if len(header) <= len(prefix) || !strings.EqualFold(header[:len(prefix)], prefix) {
		return "", false
	}
	tok := strings.TrimSpace(header[len(prefix):])
	if tok == "" {
		return "", false
	}
	return tok, true
}

// ConstantTimeEqual 用于需要恒定时间比较的场景（如调试开关的共享密钥）。
func ConstantTimeEqual(a, b string) bool {
	return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}
