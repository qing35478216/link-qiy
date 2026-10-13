package ssrf

import (
	"context"
	"errors"
	"net/http"
	"net/netip"
	"testing"

	"github.com/linkai/gateway/internal/domain"
)

// fakeResolver 是可控的 DNS 解析器，用于确定性地测试解析后校验。
type fakeResolver struct {
	// addrs 是解析结果。
	addrs []netip.Addr
	// err 是解析错误。
	err error
	// calls 记录被解析过的主机名。
	calls []string
}

// LookupNetIP 实现 resolver。
func (f *fakeResolver) LookupNetIP(_ context.Context, _, host string) ([]netip.Addr, error) {
	f.calls = append(f.calls, host)
	if f.err != nil {
		return nil, f.err
	}
	return f.addrs, nil
}

// publicResolver 返回一个固定解析到公网 IP 的解析器。
func publicResolver(t *testing.T, ip string) *fakeResolver {
	t.Helper()
	addr, err := netip.ParseAddr(ip)
	if err != nil {
		t.Fatalf("parse %q: %v", ip, err)
	}
	return &fakeResolver{addrs: []netip.Addr{addr}}
}

// TestValidate_BlocksPrivateAddresses 是工单验收标准 4 的核心用例：
// 各类内网/保留地址必须被拦截。
func TestValidate_BlocksPrivateAddresses(t *testing.T) {
	t.Parallel()

	// 每个目标都用"IP 字面量"形式，避免依赖真实 DNS。
	cases := []struct {
		name string
		url  string
	}{
		{"回环地址", "http://127.0.0.1/admin"},
		{"回环地址带端口", "http://127.0.0.1:6379/"},
		{"回环 IPv6", "http://[::1]:8080/"},
		{"RFC1918 十进制段", "http://10.0.0.1/internal"},
		{"RFC1918 172 段", "http://172.16.0.5/admin"},
		{"RFC1918 192 段", "http://192.168.1.1/admin"},
		{"云元数据（AWS/GCP 通用）", "http://169.254.169.254/latest/meta-data/"},
		{"云元数据 IPv6", "http://[fd00:ec2::254]/latest/meta-data/"},
		{"链路本地", "http://169.254.10.1/"},
		{"CGNAT 100.64 段", "http://100.64.0.1/"},
		{"组播", "http://239.1.1.1/"},
		{"未指定地址", "http://0.0.0.0/"},
		{"文档保留段", "http://192.0.2.1/"},
		{"广播地址", "http://255.255.255.255/"},
		{"localhost 主机名", "http://localhost:8080/"},
		{"localhost 子域", "http://api.localhost/"},
		{"GCP 元数据主机名", "http://metadata.google.internal/"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			// IP 字面量不触发 DNS 解析，用空解析器即可。
			g := New(WithResolver(&fakeResolver{}))
			_, err := g.Validate(context.Background(), tc.url)
			if !errors.Is(err, domain.ErrForbiddenTarget) {
				t.Fatalf("url %s: err = %v, want ErrForbiddenTarget", tc.url, err)
			}
		})
	}
}

// TestValidate_BlocksPrivateViaDNS 验证域名解析到内网 IP 时被拦截。
//
// 这是最常见的绕过：URL 看起来正常，但域名解析到 10.x 内网地址。
func TestValidate_BlocksPrivateViaDNS(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		ip   string
	}{
		{"解析到十进制段", "10.1.2.3"},
		{"解析到元数据地址", "169.254.169.254"},
		{"解析到回环", "127.0.0.1"},
		{"解析到 192.168", "192.168.100.1"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			g := New(WithResolver(publicResolver(t, tc.ip)))
			_, err := g.Validate(context.Background(), "https://attacker.example.com/callback")
			if !errors.Is(err, domain.ErrForbiddenTarget) {
				t.Fatalf("resolved to %s: err = %v, want ErrForbiddenTarget", tc.ip, err)
			}
		})
	}
}

// TestValidate_AllowsPublicAddress 验证公网地址正常放行。
func TestValidate_AllowsPublicAddress(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(publicResolver(t, "93.184.216.34")))
	addr, err := g.Validate(context.Background(), "https://example.com/webhook")
	if err != nil {
		t.Fatalf("public address should pass, got %v", err)
	}
	if addr != "93.184.216.34:443" {
		t.Fatalf("addr = %q, want %q", addr, "93.184.216.34:443")
	}
}

// TestValidate_RejectsOneBadAddressInSet 验证多 A 记录中只要有一个内网就拒绝。
//
// 攻击者常用 DNS 轮询：先返回公网 IP 通过校验，再返回内网 IP 命中内网服务。
func TestValidate_RejectsOneBadAddressInSet(t *testing.T) {
	t.Parallel()

	res := &fakeResolver{addrs: []netip.Addr{
		netip.MustParseAddr("93.184.216.34"),
		netip.MustParseAddr("169.254.169.254"),
	}}
	g := New(WithResolver(res))

	if _, err := g.Validate(context.Background(), "https://rebind.example.com/"); !errors.Is(err, domain.ErrForbiddenTarget) {
		t.Fatalf("err = %v, want ErrForbiddenTarget when any address is private", err)
	}
}

// TestValidate_BlocksIPv6TransitionBypass 验证 6to4/Teredro/NAT64 内嵌私网 IPv4 被拦截。
//
// 这类地址字面上是公网 IPv6，但内嵌的 IPv4 是内网地址，
// 是绕过"只检查 IPv6 前缀"逻辑的经典手法。
func TestValidate_BlocksIPv6TransitionBypass(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		ip   string
	}{
		{"6to4 内嵌 10.x", "2002:0a00:0001::1"},
		{"6to4 内嵌 127.0.0.1", "2002:7f00:0001::1"},
		{"NAT64 内嵌 169.254.169.254", "64:ff9b::a9fe:a9fe"},
		{"Teredro 内嵌 10.x", "2001:0000:0000:0000:0000:0000:0000:0001"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if IsPublicAddr(netip.MustParseAddr(tc.ip)) {
				t.Fatalf("%s should not be considered public", tc.ip)
			}
			// 走完整校验链路，确认内嵌私网 IPv4 的 IPv6 地址也会被拦。
			g := New()
			_, err := g.Validate(context.Background(), "http://["+tc.ip+"]/callback")
			if !errors.Is(err, domain.ErrForbiddenTarget) {
				t.Fatalf("Validate(%s) err = %v, want ErrForbiddenTarget", tc.ip, err)
			}
		})
	}
}

// TestValidate_BlocksNonHTTPSchemes 验证非 http/https 协议被拒。
func TestValidate_BlocksNonHTTPSchemes(t *testing.T) {
	t.Parallel()

	for _, raw := range []string{
		"file:///etc/passwd",
		"gopher://127.0.0.1:6379/_INFO",
		"ftp://example.com/x",
		"dict://example.com:11211/stat",
		"gopher+unix:///var/run/docker.sock",
	} {
		t.Run(raw, func(t *testing.T) {
			t.Parallel()
			g := New(WithResolver(publicResolver(t, "93.184.216.34")))
			_, err := g.Validate(context.Background(), raw)
			if !errors.Is(err, domain.ErrMalformedTarget) {
				t.Fatalf("err = %v, want ErrMalformedTarget", err)
			}
		})
	}
}

// TestValidate_BlocksUserinfo 验证带 userinfo 的 URL 被拒。
func TestValidate_BlocksUserinfo(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(publicResolver(t, "93.184.216.34")))
	_, err := g.Validate(context.Background(), "https://user:pass@example.com/")
	if !errors.Is(err, domain.ErrMalformedTarget) {
		t.Fatalf("err = %v, want ErrMalformedTarget", err)
	}
}

// TestValidate_BlocksNonStandardPort 验证非常规端口被拒。
//
// 只放行 80/443 可挡住针对 6379/9200/11211 等内部服务的端口扫描。
func TestValidate_BlocksNonStandardPort(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(publicResolver(t, "93.184.216.34")))
	_, err := g.Validate(context.Background(), "https://example.com:8443/admin")
	if !errors.Is(err, domain.ErrForbiddenTarget) {
		t.Fatalf("err = %v, want ErrForbiddenTarget", err)
	}
}

// TestValidate_AllowsConfiguredPort 验证白名单端口放行。
func TestValidate_AllowsConfiguredPort(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(publicResolver(t, "93.184.216.34")), WithAllowedPorts(8443))
	if _, err := g.Validate(context.Background(), "https://example.com:8443/admin"); err != nil {
		t.Fatalf("configured port should pass, got %v", err)
	}
}

// TestValidate_MalformedURL 验证畸形 URL 被拒。
func TestValidate_MalformedURL(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(publicResolver(t, "93.184.216.34")))
	for _, raw := range []string{"", "://missing-scheme", "https://", "http://"} {
		_, err := g.Validate(context.Background(), raw)
		if err == nil {
			t.Errorf("url %q should be rejected", raw)
		}
	}
}

// TestValidate_DNSFailure 验证解析失败不放行。
func TestValidate_DNSFailure(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(&fakeResolver{err: errors.New("NXDOMAIN")}))
	_, err := g.Validate(context.Background(), "https://does-not-exist.example.com/")
	if !errors.Is(err, domain.ErrForbiddenTarget) {
		t.Fatalf("err = %v, want ErrForbiddenTarget", err)
	}
}

// TestValidate_AllowlistPermitsInternalHost 验证白名单主机可访问内网。
//
// 受控场景：平台需要调用自己部署在内网的服务。这必须显式配置，
// 不能靠放宽全局开关。
func TestValidate_AllowlistPermitsInternalHost(t *testing.T) {
	t.Parallel()

	res := &fakeResolver{addrs: []netip.Addr{netip.MustParseAddr("10.0.0.5")}}

	// 不在白名单：拦截。
	strict := New(WithResolver(res))
	if _, err := strict.Validate(context.Background(), "http://internal.svc/webhook"); !errors.Is(err, domain.ErrForbiddenTarget) {
		t.Fatalf("non-allowlisted internal host should be blocked, got %v", err)
	}

	// 在白名单：放行。
	permissive := New(WithResolver(res), WithAllowedHosts("internal.svc"))
	if _, err := permissive.Validate(context.Background(), "http://internal.svc/webhook"); err != nil {
		t.Fatalf("allowlisted host should pass, got %v", err)
	}
}

// TestPrivateRangesFlagRelaxesForLocalDev 验证开发开关只影响 IP 校验，
// 不影响端口限制（端口仍需显式放行）。
func TestPrivateRangesFlagRelaxesForLocalDev(t *testing.T) {
	t.Parallel()

	res := &fakeResolver{addrs: []netip.Addr{netip.MustParseAddr("127.0.0.1")}}

	// 80 端口 + 私网开关 + 主机白名单：回环可达。
	g := New(WithResolver(res), WithPrivateRanges(true), WithAllowedHosts("localhost"))
	if _, err := g.Validate(context.Background(), "http://localhost/"); err != nil {
		t.Fatalf("private ranges flag should permit loopback, got %v", err)
	}

	// 端口限制依然生效：8080 未在允许列表内。
	if _, err := g.Validate(context.Background(), "http://localhost:8080/"); !errors.Is(err, domain.ErrForbiddenTarget) {
		t.Fatalf("port restriction must still apply, got %v", err)
	}
}

// TestIsPublicAddr 表格测试公网地址判定。
func TestIsPublicAddr(t *testing.T) {
	t.Parallel()

	cases := []struct {
		ip     string
		public bool
	}{
		{"8.8.8.8", true},
		{"1.1.1.1", true},
		{"93.184.216.34", true},
		{"172.32.0.1", true}, // 172.16/12 之外
		{"100.63.255.255", true},
		{"10.0.0.1", false},
		{"172.16.0.1", false},
		{"172.31.255.255", false},
		{"192.168.0.1", false},
		{"127.0.0.1", false},
		{"169.254.169.254", false},
		{"100.64.0.1", false},
		{"100.127.255.255", false},
		{"0.0.0.0", false},
		{"255.255.255.255", false},
		{"224.0.0.1", false},
		{"::1", false},
		{"fe80::1", false},
		{"fc00::1", false},
		{"2606:4700:4700::1111", true},
	}
	for _, tc := range cases {
		got := IsPublicAddr(netip.MustParseAddr(tc.ip))
		if got != tc.public {
			t.Errorf("IsPublicAddr(%s) = %v, want %v", tc.ip, got, tc.public)
		}
	}
}

// TestIsPublicAddr_InvalidAddr 验证非法地址一律判为不可公网路由。
func TestIsPublicAddr_InvalidAddr(t *testing.T) {
	t.Parallel()

	if IsPublicAddr(netip.Addr{}) {
		t.Error("invalid address must not be considered public")
	}
}

// TestTransportDisablesProxy 验证出站 transport 显式禁用了环境代理。
//
// 否则 HTTP_PROXY 环境变量会让请求绕过本守卫直连，是常见的绕过路径。
func TestTransportDisablesProxy(t *testing.T) {
	t.Parallel()

	g := New()
	if g.Transport().Proxy != nil {
		t.Fatal("transport must not use an HTTP proxy, otherwise the guard is bypassable")
	}
}

// TestClientRevalidatesRedirects 验证重定向每一跳都重新校验。
func TestClientRevalidatesRedirects(t *testing.T) {
	t.Parallel()

	g := New(WithResolver(publicResolver(t, "93.184.216.34")))
	client := g.Client()
	if client.CheckRedirect == nil {
		t.Fatal("client must validate redirects")
	}
	// 构造一个跳向内网的请求，CheckRedirect 应拒绝。
	req, err := http.NewRequestWithContext(context.Background(), "GET", "http://169.254.169.254/", nil)
	if err != nil {
		t.Fatalf("build request: %v", err)
	}
	if err := client.CheckRedirect(req, nil); err == nil {
		t.Fatal("redirect to metadata endpoint must be rejected")
	}
}
