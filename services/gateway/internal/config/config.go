// Package config 定义网关的启动配置。
//
// 配置来源为环境变量（部署时注入），不读配置文件——避免密钥落盘。
// 所有字段都有安全默认值，唯独签名密钥必须显式提供（见 Load）。
package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config 是网关完整配置。
type Config struct {
	// Addr 监听地址。
	Addr string
	// ReadTimeout 读超时。
	ReadTimeout time.Duration
	// WriteTimeout 写超时。注意：SSE/流式响应需调大或设为 0。
	WriteTimeout time.Duration

	// JWTSecret JWT HS256 签名密钥，必须 ≥32 字节。必填。
	JWTSecret string
	// JWTIssuer 签发方校验，空则不校验。
	JWTIssuer string
	// JWTLeeway 时钟偏移容忍。
	JWTLeeway time.Duration

	// TenantRate 租户级限流：窗口内请求数。
	TenantRate int
	// TenantWindow 租户级限流窗口。
	TenantWindow time.Duration
	// KeyRate 凭证级限流：窗口内请求数，0 表示不启用该维度。
	KeyRate int
	// KeyWindow 凭证级限流窗口。
	KeyWindow time.Duration
	// EndpointRate 端点级限流：窗口内请求数，0 表示不启用该维度。
	EndpointRate int
	// EndpointWindow 端点级限流窗口。
	EndpointWindow time.Duration

	// CORSConsoleOrigins 控制台允许来源，逗号分隔。
	CORSConsoleOrigins []string
	// CORSServiceOrigins 开放 API 允许来源，逗号分隔。
	CORSServiceOrigins []string
	// CORSEmbedOrigins 嵌入场景允许来源，逗号分隔。
	CORSEmbedOrigins []string
	// CORSAllowCredentials 是否允许携带凭证。
	CORSAllowCredentials bool

	// Upstreams 后端服务表，格式 "name=target=surface"。
	Upstreams []UpstreamConfig
	// Routes 路由表，格式 "METHOD /prefix upstream"。
	Routes []RouteConfig
}

// UpstreamConfig 是一个后端服务配置。
type UpstreamConfig struct {
	Name           string
	Target         string
	Surface        string
	RequiredScopes []string
}

// RouteConfig 是一条路由配置。
type RouteConfig struct {
	Method     string
	PathPrefix string
	Upstream   string
}

// 环境变量名。
const (
	envAddr              = "GATEWAY_ADDR"
	envJWTSecret         = "GATEWAY_JWT_SECRET"
	envJWTIssuer         = "GATEWAY_JWT_ISSUER"
	envJWTLeeway         = "GATEWAY_JWT_LEEWAY"
	envTenantRate        = "GATEWAY_TENANT_RATE"
	envTenantWindow      = "GATEWAY_TENANT_WINDOW"
	envKeyRate           = "GATEWAY_KEY_RATE"
	envKeyWindow         = "GATEWAY_KEY_WINDOW"
	envEndpointRate      = "GATEWAY_ENDPOINT_RATE"
	envEndpointWindow    = "GATEWAY_ENDPOINT_WINDOW"
	envCORSConsoleOrigin = "GATEWAY_CORS_CONSOLE_ORIGINS"
	envCORSSvcOrigin     = "GATEWAY_CORS_SERVICE_ORIGINS"
	envCORSEmbedOrigin   = "GATEWAY_CORS_EMBED_ORIGINS"
	envCORSCredentials   = "GATEWAY_CORS_ALLOW_CREDENTIALS"
	envUpstreams         = "GATEWAY_UPSTREAMS"
	envRoutes            = "GATEWAY_ROUTES"

	// minJWTSecretLen 是签名密钥最小长度。HS256 用短密钥可被离线爆破。
	minJWTSecretLen = 32
)

// Load 从环境变量装配配置，并做启动期校验。
//
// 校验失败一律返回 error 而非 panic：部署系统需要看到明确的失败原因，
// 而不是一坨堆栈。调用方负责终止进程。
func Load() (*Config, error) {
	c := &Config{
		Addr:                 envOr(envAddr, ":8080"),
		ReadTimeout:          15 * time.Second,
		WriteTimeout:         0, // 流式响应不设写超时
		JWTSecret:            os.Getenv(envJWTSecret),
		JWTIssuer:            os.Getenv(envJWTIssuer),
		JWTLeeway:            5 * time.Second,
		TenantRate:           envIntOr(envTenantRate, 1000),
		TenantWindow:         envDurationOr(envTenantWindow, time.Minute),
		KeyRate:              envIntOr(envKeyRate, 200),
		KeyWindow:            envDurationOr(envKeyWindow, time.Minute),
		EndpointRate:         envIntOr(envEndpointRate, 300),
		EndpointWindow:       envDurationOr(envEndpointWindow, time.Minute),
		CORSConsoleOrigins:   envListOr(envCORSConsoleOrigin, []string{"http://localhost:5173"}),
		CORSServiceOrigins:   envListOr(envCORSSvcOrigin, []string{}),
		CORSEmbedOrigins:     envListOr(envCORSEmbedOrigin, []string{}),
		CORSAllowCredentials: envBoolOr(envCORSCredentials, false),
		Upstreams:            parseUpstreams(os.Getenv(envUpstreams)),
		Routes:               parseRoutes(os.Getenv(envRoutes)),
	}

	// 时钟偏移可配，其余超时保持默认。
	if v := os.Getenv(envJWTLeeway); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", envJWTLeeway, err)
		}
		c.JWTLeeway = d
	}

	if err := c.Validate(); err != nil {
		return nil, err
	}
	return c, nil
}

// Validate 校验配置合法性。
func (c *Config) Validate() error {
	// 签名密钥是硬性要求：缺失即意味着任何人都能伪造令牌。
	if len(c.JWTSecret) < minJWTSecretLen {
		return fmt.Errorf("%s: must be at least %d bytes, got %d",
			envJWTSecret, minJWTSecretLen, len(c.JWTSecret))
	}
	if c.TenantRate <= 0 || c.TenantWindow <= 0 {
		return errors.New("tenant rate limit must be positive")
	}
	if c.KeyRate < 0 || c.KeyRate > 0 && c.KeyWindow <= 0 {
		return errors.New("key rate limit window must be positive when rate > 0")
	}
	if c.EndpointRate < 0 || c.EndpointRate > 0 && c.EndpointWindow <= 0 {
		return errors.New("endpoint rate limit window must be positive when rate > 0")
	}
	if len(c.Upstreams) == 0 {
		return errors.New("at least one upstream is required")
	}
	return nil
}

// envOr 读字符串环境变量，为空时用默认值。
func envOr(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

// envListOr 读逗号分隔的环境变量，为空时用默认值。
func envListOr(key string, def []string) []string {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// envIntOr 读整型环境变量。
func envIntOr(key string, def int) int {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 0 {
		return def
	}
	return n
}

// envBoolOr 读布尔环境变量。
func envBoolOr(key string, def bool) bool {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}

// envDurationOr 读时长环境变量。
func envDurationOr(key string, def time.Duration) time.Duration {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil || d <= 0 {
		return def
	}
	return d
}

// parseUpstreams 解析 "name=target=surface[,scope1|scope2];..." 形式。
func parseUpstreams(raw string) []UpstreamConfig {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	var out []UpstreamConfig
	for _, entry := range strings.Split(raw, ";") {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}
		parts := strings.SplitN(entry, "=", 3)
		if len(parts) < 2 {
			continue
		}
		uc := UpstreamConfig{
			Name:   strings.TrimSpace(parts[0]),
			Target: strings.TrimSpace(parts[1]),
		}
		if len(parts) == 3 {
			fields := strings.SplitN(parts[2], "|", 2)
			uc.Surface = strings.TrimSpace(fields[0])
			if len(fields) == 2 {
				for _, s := range strings.Split(fields[1], ",") {
					if s = strings.TrimSpace(s); s != "" {
						uc.RequiredScopes = append(uc.RequiredScopes, s)
					}
				}
			}
		}
		out = append(out, uc)
	}
	return out
}

// parseRoutes 解析 "METHOD /prefix upstream;..." 形式。
func parseRoutes(raw string) []RouteConfig {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	var out []RouteConfig
	for _, entry := range strings.Split(raw, ";") {
		fields := strings.Fields(strings.TrimSpace(entry))
		if len(fields) != 3 {
			continue
		}
		out = append(out, RouteConfig{
			Method:     fields[0],
			PathPrefix: fields[1],
			Upstream:   fields[2],
		})
	}
	return out
}
