package ssrf

import (
	"context"
	"net/netip"
	"testing"
)

// GATE-1: 独立门禁评审自建绕过用例（非实现者自测）。
// 目标是确认 SSRF 闸门对各种编码/变形 IP 的实际拦截行为，
// 而不是相信 blockedHostnames 与 IsPublicAddr 的注释声明。
func TestGate_IPLiteralBypassMatrix(t *testing.T) {
	cases := []struct {
		name    string
		url     string
		blocked bool
	}{
		// 归一化到 127.0.0.1 的各种写法
		{"ipv4-dotted", "http://127.0.0.1/x", true},
		{"ipv4-decimal-2130706433", "http://2130706433/x", true},
		{"ipv4-hex-0x7f000001", "http://0x7f000001/x", true},
		{"ipv4-hex-short-0x7f.0.0.1", "http://0x7f.0.0.1/x", true},
		{"ipv4-octal-0177.0.0.1", "http://0177.0.0.1/x", true},
		{"ipv4-mixed-017700000001", "http://017700000001/x", true},
		{"ipv4-short-127.1", "http://127.1/x", true},
		{"ipv4-dotted-trailing-dot", "http://127.0.0.1./x", true},
		{"ipv4-loopback-alt-127.255.255.254", "http://127.255.255.254/x", true},
		{"ipv4-localhost-literal", "http://localhost/x", true},

		// IPv6 / IPv4-mapped IPv6
		{"ipv6-loopback", "http://[::1]/x", true},
		{"ipv6-mapped-loopback", "http://[::ffff:127.0.0.1]/x", true},
		{"ipv6-mapped-metadata", "http://[::ffff:169.254.169.254]/x", true},
		{"ipv6-ula-fc00", "http://[fc00::1]/x", true},
		{"ipv6-ula-fd00", "http://[fd00::1]/x", true},
		{"ipv6-6to4-embed-loopback", "http://[2002:7f00:0001::1]/x", true},
		{"ipv6-nat64-embed-loopback", "http://[64:ff9b::7f00:1]/x", true},
		{"ipv6-teredo-embed-loopback", "http://[2001:0:0:0:0:0:8080:8081]/x", true},

		// 云元数据 / 内网
		{"metadata-aws", "http://169.254.169.254/latest/meta-data/", true},
		{"metadata-gcp", "http://metadata.google.internal/computeMetadata/v1/", true},
		{"rfc1918-10", "http://10.0.0.1/x", true},
		{"rfc1918-172", "http://172.16.0.1/x", true},
		{"rfc1918-192", "http://192.168.1.1/x", true},
		{"cgnat", "http://100.64.0.1/x", true},
		{"link-local", "http://169.254.1.1/x", true},
		{"unspecified", "http://0.0.0.0/x", true},
		{"reserved-240", "http://240.0.0.1/x", true},

		// 非 IP scheme 变形
		{"scheme-file", "file:///etc/passwd", true},
		{"scheme-gopher", "gopher://127.0.0.1:6379/_x", true},
		{"scheme-ftp", "ftp://127.0.0.1/x", true},
		{"userinfo-confusion", "http://allowed.com@127.0.0.1/x", true},
		{"port-priv-high", "http://127.0.0.1:22/x", true},
	}

	g := New(WithResolver(staticResolver{}))
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := g.Validate(context.Background(), c.url)
			got := err != nil
			if got != c.blocked {
				t.Errorf("SECURITY: url=%q want_blocked=%v got_blocked=%v err=%v",
					c.url, c.blocked, got, err)
			} else {
				t.Logf("OK url=%q blocked=%v err=%v", c.url, got, err)
			}
		})
	}
}

// staticResolver 对任何域名返回内网地址，模拟恶意 DNS。
type staticResolver struct{}

func (staticResolver) LookupNetIP(_ context.Context, _, host string) ([]netip.Addr, error) {
	return []netip.Addr{netip.MustParseAddr("10.1.2.3")}, nil
}

// GATE-2: 恶意 DNS 把域名解析到内网 —— 必须拦截。
func TestGate_MaliciousDNSResolvingToPrivate(t *testing.T) {
	g := New(WithResolver(staticResolver{}))
	if _, err := g.Validate(context.Background(), "http://totally-legit.example.com/x"); err == nil {
		t.Fatal("SECURITY: 恶意 DNS 解析到 10.1.2.3 却放行")
	} else {
		t.Logf("OK 恶意DNS被拦截: %v", err)
	}
}

// GATE-3: 显式白名单是否会成为万能后门 —— 白名单主机解析到内网时是否放行。
// 若放行，则白名单 = SSRF 豁免，需要在评审里定性。
func TestGate_WhitelistAllowsPrivate(t *testing.T) {
	g := New(WithAllowedHosts("legit.example.com"), WithResolver(staticResolver{}))
	target, err := g.Validate(context.Background(), "http://legit.example.com/x")
	t.Logf("白名单主机解析到内网时：target=%q err=%v", target, err)
	if err == nil {
		t.Log("FINDING: 白名单主机解析到 10.1.2.3 仍被放行（白名单等价于 SSRF 豁免）")
	}
}

// GATE-4: 拨号层（第 3 层防御）是否真的独立生效 —— 绕过 Validate 直接调 DialContext。
func TestGate_DialContextDirectOnPrivate(t *testing.T) {
	g := New(WithResolver(staticResolver{}))
	conn, err := g.DialContext(context.Background(), "tcp", "evil.example.com:80")
	if conn != nil {
		_ = conn.Close()
	}
	if err == nil {
		t.Fatal("SECURITY: DialContext 直连 evil.example.com:80 未被拦截")
	}
	t.Logf("OK DialContext 拦截: %v", err)
}

// GATE-5: DialContext 对字面 IP（含 IPv6-mapped）的拦截。
func TestGate_DialContextLiteralIPs(t *testing.T) {
	g := New()
	for _, addr := range []string{
		"127.0.0.1:80", "169.254.169.254:80", "10.0.0.1:80",
		"[::1]:80", "[::ffff:127.0.0.1]:80", "[fd00::1]:80",
		"2130706433:80", "0x7f000001:80",
	} {
		conn, err := g.DialContext(context.Background(), "tcp", addr)
		if conn != nil {
			_ = conn.Close()
		}
		t.Logf("addr=%-24s blocked=%v err=%v", addr, err != nil, err)
		if err == nil {
			t.Errorf("SECURITY: DialContext 放行 %s", addr)
		}
	}
}
