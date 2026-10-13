package config

import (
	"strings"
	"testing"
	"time"
)

// validSecret 是一份合法的测试密钥。
const validSecret = "config-test-secret-at-least-32-characters"

// baseConfig 返回一份可通过校验的最小配置。
func baseConfig() *Config {
	return &Config{
		JWTSecret:    validSecret,
		TenantRate:   100,
		TenantWindow: time.Minute,
		Upstreams: []UpstreamConfig{
			{Name: "platform", Target: "http://platform:8001"},
		},
	}
}

// TestValidate 覆盖配置校验的各条规则。
func TestValidate(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		mutate  func(*Config)
		wantErr bool
	}{
		{"最小合法配置", func(*Config) {}, false},
		{"JWT 密钥为空", func(c *Config) { c.JWTSecret = "" }, true},
		{"JWT 密钥过短", func(c *Config) { c.JWTSecret = "short" }, true},
		{"租户级配额为零", func(c *Config) { c.TenantRate = 0 }, true},
		{"租户级窗口为零", func(c *Config) { c.TenantWindow = 0 }, true},
		{"凭证级配额为负", func(c *Config) { c.KeyRate = -1 }, true},
		{"凭证级有配额但窗口为零", func(c *Config) { c.KeyRate = 10; c.KeyWindow = 0 }, true},
		{"端点级有配额但窗口为零", func(c *Config) { c.EndpointRate = 10; c.EndpointWindow = 0 }, true},
		{"无上游", func(c *Config) { c.Upstreams = nil }, true},
		{"恰好 32 字节密钥", func(c *Config) { c.JWTSecret = strings.Repeat("x", 32) }, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cfg := baseConfig()
			tc.mutate(cfg)
			err := cfg.Validate()
			if tc.wantErr && err == nil {
				t.Fatal("expected validation error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected validation error: %v", err)
			}
		})
	}
}

// TestValidateZeroRateDisablesDimension 验证配额为 0 表示关闭该维度而非非法。
func TestValidateZeroRateDisablesDimension(t *testing.T) {
	t.Parallel()

	cfg := baseConfig()
	cfg.KeyRate = 0
	cfg.EndpointRate = 0
	if err := cfg.Validate(); err != nil {
		t.Fatalf("zero rate should disable the dimension, got %v", err)
	}
}

// TestLoadFromEnv 验证环境变量装配。
func TestLoadFromEnv(t *testing.T) {
	t.Setenv(envJWTSecret, validSecret)
	t.Setenv(envAddr, ":9999")
	t.Setenv(envTenantRate, "250")
	t.Setenv(envTenantWindow, "30s")
	t.Setenv(envCORSConsoleOrigin, "https://a.example.com, https://b.example.com")
	t.Setenv(envUpstreams, "platform=http://p:8001=console;runtime=http://r:8002=service|app:read")
	t.Setenv(envRoutes, "GET /console/api platform; POST /service/api runtime")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Addr != ":9999" {
		t.Errorf("Addr = %q, want :9999", cfg.Addr)
	}
	if cfg.TenantRate != 250 {
		t.Errorf("TenantRate = %d, want 250", cfg.TenantRate)
	}
	if cfg.TenantWindow != 30*time.Second {
		t.Errorf("TenantWindow = %v, want 30s", cfg.TenantWindow)
	}
	if len(cfg.CORSConsoleOrigins) != 2 {
		t.Errorf("CORSConsoleOrigins = %v, want 2 entries", cfg.CORSConsoleOrigins)
	}
	if len(cfg.Upstreams) != 2 {
		t.Fatalf("len(Upstreams) = %d, want 2", len(cfg.Upstreams))
	}
	if cfg.Upstreams[1].Surface != "service" {
		t.Errorf("Surface = %q, want service", cfg.Upstreams[1].Surface)
	}
	if len(cfg.Upstreams[1].RequiredScopes) != 1 {
		t.Errorf("RequiredScopes = %v, want 1 entry", cfg.Upstreams[1].RequiredScopes)
	}
	if len(cfg.Routes) != 2 {
		t.Fatalf("len(Routes) = %d, want 2", len(cfg.Routes))
	}
}

// TestLoadFailsWithoutSecret 验证缺密钥时启动失败。
func TestLoadFailsWithoutSecret(t *testing.T) {
	t.Setenv(envJWTSecret, "")

	if _, err := Load(); err == nil {
		t.Fatal("Load must fail without a JWT secret")
	}
}

// TestParseUpstreams 覆盖上游解析的容错。
func TestParseUpstreams(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name  string
		raw   string
		count int
	}{
		{"空串", "", 0},
		{"单条", "a=http://a", 1},
		{"多条", "a=http://a;b=http://b", 2},
		{"尾部分号", "a=http://a;", 1},
		{"跳过畸形项", "a=http://a;broken;b=http://b", 2},
		{"多余等号归入第三段", "a=http://a=surface=x", 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := parseUpstreams(tc.raw)
			if len(got) != tc.count {
				t.Errorf("parseUpstreams(%q) = %d entries, want %d", tc.raw, len(got), tc.count)
			}
		})
	}
}

// TestParseRoutes 覆盖路由解析的容错。
func TestParseRoutes(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name  string
		raw   string
		count int
	}{
		{"空串", "", 0},
		{"单条", "GET /a upstream", 1},
		{"多条", "GET /a u1; POST /b u2", 2},
		{"跳过字段不足项", "GET /a u1;BROKEN;POST /b u2", 2},
		{"多余字段被跳过", "GET /a u1 EXTRA", 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := parseRoutes(tc.raw)
			if len(got) != tc.count {
				t.Errorf("parseRoutes(%q) = %d entries, want %d", tc.raw, len(got), tc.count)
			}
		})
	}
}

// TestEnvIntOrFallsBackOnInvalid 验证非法整数回退到默认值。
func TestEnvIntOrFallsBackOnInvalid(t *testing.T) {
	t.Setenv("TEST_INT", "not-a-number")

	if got := envIntOr("TEST_INT", 42); got != 42 {
		t.Errorf("envIntOr = %d, want 42", got)
	}
	t.Setenv("TEST_INT", "-5")
	if got := envIntOr("TEST_INT", 42); got != 42 {
		t.Errorf("envIntOr with negative = %d, want 42 (negative rejected)", got)
	}
}

// TestEnvBoolOr 验证布尔解析。
func TestEnvBoolOr(t *testing.T) {
	t.Setenv("TEST_BOOL", "true")
	if !envBoolOr("TEST_BOOL", false) {
		t.Error("expected true")
	}
	t.Setenv("TEST_BOOL", "nonsense")
	if !envBoolOr("TEST_BOOL", true) {
		t.Error("invalid value should fall back to the default")
	}
}

// TestEnvDurationOr 验证时长解析。
func TestEnvDurationOr(t *testing.T) {
	t.Setenv("TEST_DUR", "2m")
	if got := envDurationOr("TEST_DUR", time.Second); got != 2*time.Minute {
		t.Errorf("envDurationOr = %v, want 2m", got)
	}
	t.Setenv("TEST_DUR", "garbage")
	if got := envDurationOr("TEST_DUR", time.Second); got != time.Second {
		t.Errorf("invalid duration should fall back, got %v", got)
	}
}
