// Package ssrf 实现出站请求的 SSRF 防护（安全基线铁律 5 的直接实现）。
//
// 威胁模型：网关/服务会按用户提供的 URL 发起出站请求（webhook 回调、
// 链接预览、从 URL 导入等）。若不设防，攻击者可用平台内网身份探测
// 169.254.169.254（云元数据）、10.0.0.0/8 内部服务、127.0.0.1 本地端口。
//
// 防御要点（三层，任一层单独都不够）：
//  1. URL 静态校验：scheme 仅允许 http/https，拒绝 userinfo、非常规端口。
//  2. DNS 解析后校验：解析出的每一个 IP 都必须可公网路由。
//  3. 连接时校验：net.Dialer.Control 在 TCP 握手前再校验一次实际连接的地址，
//     防 DNS rebinding（校验时解析到公网 IP，连接时解析到内网 IP 的 TOCTOU 攻击）。
package ssrf

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/linkai/gateway/internal/domain"
)

// Guard 是出站目标守卫。
type Guard struct {
	// allowedHosts 白名单主机（精确匹配）。为空表示不限制主机，
	// 但仍强制执行 IP 可公网路由校验。
	allowedHosts map[string]struct{}
	// allowedPorts 额外允许的端口。80/443 始终允许。
	allowedPorts map[uint16]struct{}
	// allowPrivateRanges 是否放行内网地址。仅本地开发/测试可为 true，
	// 生产必须保持 false——这是整个模块存在的意义。
	allowPrivateRanges bool
	// resolver DNS 解析器，可注入以便测试。
	resolver resolver
	// maxRedirects 跟随重定向的最大跳数。
	maxRedirects int
}

// resolver 是 DNS 解析接口，便于测试注入假解析结果。
type resolver interface {
	LookupNetIP(ctx context.Context, network, host string) ([]netip.Addr, error)
}

// Option 是 Guard 的构造选项。
type Option func(*Guard)

// WithAllowedHosts 设置主机白名单。命中白名单时仍要求该主机解析到公网 IP，
// 白名单只放宽"域名形态"限制，不放宽 IP 限制——除非同时开启 WithPrivateRanges。
func WithAllowedHosts(hosts ...string) Option {
	return func(g *Guard) {
		g.allowedHosts = make(map[string]struct{}, len(hosts))
		for _, h := range hosts {
			h = strings.ToLower(strings.TrimSpace(h))
			if h == "" {
				continue
			}
			g.allowedHosts[h] = struct{}{}
		}
	}
}

// WithAllowedPorts 设置额外允许的端口。
func WithAllowedPorts(ports ...uint16) Option {
	return func(g *Guard) {
		g.allowedPorts = make(map[uint16]struct{}, len(ports))
		for _, p := range ports {
			g.allowedPorts[p] = struct{}{}
		}
	}
}

// WithPrivateRanges 放行内网地址。仅限本地开发与单测，生产严禁开启。
func WithPrivateRanges(allow bool) Option {
	return func(g *Guard) { g.allowPrivateRanges = allow }
}

// WithResolver 注入 DNS 解析器，供测试使用。
func WithResolver(r resolver) Option {
	return func(g *Guard) {
		if r != nil {
			g.resolver = r
		}
	}
}

// WithMaxRedirects 设置最大重定向跳数。
func WithMaxRedirects(n int) Option {
	return func(g *Guard) {
		if n >= 0 {
			g.maxRedirects = n
		}
	}
}

// New 创建出站守卫。
func New(opts ...Option) *Guard {
	g := &Guard{
		allowedPorts: map[uint16]struct{}{80: {}, 443: {}},
		resolver:     net.DefaultResolver,
		maxRedirects: 3,
	}
	for _, opt := range opts {
		opt(g)
	}
	return g
}

// Validate 对出站 URL 做静态校验 + DNS 解析后校验。
//
// 返回校验通过后可直接拨号的目标地址——调用方应当连这个 IP 而非原域名，
// 这样 DNS 只解析一次，消灭 rebinding 的时间窗。
func (g *Guard) Validate(ctx context.Context, rawURL string) (string, error) {
	u, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return "", fmt.Errorf("%w: %s", domain.ErrMalformedTarget, err)
	}
	return g.ValidateParsed(ctx, u)
}

// ValidateParsed 是 Validate 的结构化版本。
func (g *Guard) ValidateParsed(ctx context.Context, u *url.URL) (string, error) {
	if u == nil {
		return "", fmt.Errorf("%w: nil url", domain.ErrMalformedTarget)
	}

	// 第 1 层：URL 静态校验。
	switch u.Scheme {
	case "http", "https":
	case "":
		return "", fmt.Errorf("%w: missing scheme", domain.ErrMalformedTarget)
	default:
		return "", fmt.Errorf("%w: scheme %q not allowed", domain.ErrMalformedTarget, u.Scheme)
	}

	// userinfo（http://user:pass@host）常被用于钓鱼与凭证混淆，一律拒绝。
	if u.User != nil {
		return "", fmt.Errorf("%w: userinfo not allowed", domain.ErrMalformedTarget)
	}

	host := u.Hostname()
	if host == "" {
		return "", fmt.Errorf("%w: empty host", domain.ErrMalformedTarget)
	}
	host = strings.ToLower(strings.TrimSuffix(host, "."))

	// 端口校验。
	port := uint16(80)
	if u.Scheme == "https" {
		port = 443
	}
	if ps := u.Port(); ps != "" {
		parsed, perr := net.LookupPort("tcp", ps)
		if perr != nil {
			return "", fmt.Errorf("%w: bad port %q", domain.ErrMalformedTarget, ps)
		}
		port = uint16(parsed)
		if _, ok := g.allowedPorts[port]; !ok {
			return "", fmt.Errorf("%w: port %d not allowed", domain.ErrForbiddenTarget, port)
		}
	}

	// 主机名黑名单：这些名字必然指向本地/元数据端点。
	// 白名单可豁免（本地开发确需访问自己的 sidecar），但必须显式配置。
	if isBlockedHostname(host) {
		if _, whitelisted := g.allowedHosts[host]; !whitelisted {
			return "", fmt.Errorf("%w: host %q is blocked", domain.ErrForbiddenTarget, host)
		}
	}

	_, whitelisted := g.allowedHosts[host]

	// 第 2 层：DNS 解析后校验。
	addrs, err := g.resolve(ctx, host)
	if err != nil {
		return "", fmt.Errorf("%w: resolve %q: %v", domain.ErrForbiddenTarget, host, err)
	}
	if len(addrs) == 0 {
		return "", fmt.Errorf("%w: host %q resolved to nothing", domain.ErrForbiddenTarget, host)
	}

	// 始终连第一个解析结果（字面 IP），确保校验的地址就是连接的地址。
	hostPort := net.JoinHostPort(addrs[0].String(), strconv.Itoa(int(port)))

	// 白名单命中则放宽 IP 公网要求（用于受控的内网出站，如内网模型厂商网关）。
	if whitelisted {
		return hostPort, nil
	}

	for _, a := range addrs {
		if !g.addrAllowed(a) {
			return "", fmt.Errorf("%w: %s resolves to non-public address %s",
				domain.ErrForbiddenTarget, host, a)
		}
	}
	return hostPort, nil
}

// resolve 解析主机名；若本身就是 IP 字面量则直接返回。
func (g *Guard) resolve(ctx context.Context, host string) ([]netip.Addr, error) {
	if addr, err := netip.ParseAddr(host); err == nil {
		return []netip.Addr{addr.Unmap()}, nil
	}
	return g.resolver.LookupNetIP(ctx, "ip", host)
}

// addrAllowed 判断单个 IP 是否允许出站。
func (g *Guard) addrAllowed(a netip.Addr) bool {
	if g.allowPrivateRanges {
		return true
	}
	a = a.Unmap()
	return IsPublicAddr(a)
}

// CheckAddr 是暴露给中间件/日志用的单 IP 校验入口。
func (g *Guard) CheckAddr(a netip.Addr) error {
	if g.addrAllowed(a) {
		return nil
	}
	return fmt.Errorf("%w: address %s is not publicly routable", domain.ErrForbiddenTarget, a)
}

// DialContext 返回一个已加固的拨号函数，可直接赋给 http.Transport.DialContext。
//
// 第 3 层防御：解析一次 → 校验每个 IP → 连字面 IP（不经二次 DNS）。
// 这样攻击者无法在"校验"与"连接"之间把域名改指向内网。
func (g *Guard) DialContext(ctx context.Context, network, addr string) (net.Conn, error) {
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		return nil, fmt.Errorf("%w: bad addr %q", domain.ErrMalformedTarget, addr)
	}

	port, err := net.LookupPort("tcp", portStr)
	if err != nil {
		return nil, fmt.Errorf("%w: bad port %q", domain.ErrMalformedTarget, portStr)
	}
	if _, ok := g.allowedPorts[uint16(port)]; !ok {
		return nil, fmt.Errorf("%w: port %d not allowed", domain.ErrForbiddenTarget, port)
	}

	addrs, err := g.resolve(ctx, host)
	if err != nil {
		return nil, fmt.Errorf("%w: resolve %q: %v", domain.ErrForbiddenTarget, host, err)
	}

	dialer := &net.Dialer{Timeout: 10 * time.Second, KeepAlive: 30 * time.Second}
	var lastErr error
	for _, a := range addrs {
		if err := g.CheckAddr(a); err != nil {
			lastErr = err
			continue
		}
		// 连字面 IP，彻底消除 rebinding 时间窗。
		conn, derr := dialer.DialContext(ctx, network, net.JoinHostPort(a.String(), portStr))
		if derr == nil {
			return conn, nil
		}
		lastErr = derr
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("%w: no usable address for %q", domain.ErrForbiddenTarget, host)
	}
	return nil, lastErr
}

// Transport 返回一个挂载了本守卫的 http.Transport。
//
// 出站请求一律用它，不要用 http.DefaultTransport——这是铁律 5 的落地点。
func (g *Guard) Transport() *http.Transport {
	return &http.Transport{
		DialContext:           g.DialContext,
		TLSHandshakeTimeout:   10 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		MaxIdleConns:          100,
		IdleConnTimeout:       90 * time.Second,
		DisableCompression:    false,
		Proxy:                 nil, // 显式禁用环境代理，避免代理绕过本守卫
	}
}

// Client 返回挂载了本守卫与重定向校验的 http.Client。
//
// 重定向每一跳都要重新校验：攻击者常用 302 把公网 URL 跳到内网。
func (g *Guard) Client() *http.Client {
	return &http.Client{
		Transport: g.Transport(),
		Timeout:   30 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) > g.maxRedirects {
				return fmt.Errorf("too many redirects")
			}
			_, err := g.ValidateParsed(req.Context(), req.URL)
			return err
		},
	}
}

// blockedHostnames 是必然指向本地或元数据端点的主机名。
var blockedHostnames = map[string]struct{}{
	"localhost":                {},
	"localhost.localdomain":    {},
	"ip6-localhost":            {},
	"ip6-loopback":             {},
	"metadata":                 {},
	"metadata.google.internal": {},
	"instance-data":            {},
}

// isBlockedHostname 判断主机名是否在黑名单。
func isBlockedHostname(host string) bool {
	_, blocked := blockedHostnames[host]
	return blocked
}

// IsPublicAddr 判断地址是否为公网可路由地址。
//
// 覆盖：未指定、回环、私有、链路本地（CGNAT/云元数据 169.254.169.254 属此类）、
// 组播、保留地址、IPv4 转换地址（6to4/Teredro/NAT64 内嵌私网 IPv4 的绕过手法）。
func IsPublicAddr(a netip.Addr) bool {
	if !a.IsValid() {
		return false
	}
	a = a.Unmap()

	if a.IsLoopback() || a.IsPrivate() || a.IsLinkLocalUnicast() ||
		a.IsLinkLocalMulticast() || a.IsInterfaceLocalMulticast() ||
		a.IsMulticast() || a.IsUnspecified() {
		return false
	}

	// CGNAT 100.64.0.0/10：不是 RFC1918，但同样不可公网路由。
	if v4 := a.As4(); isCGNAT(v4) {
		return false
	}
	// 文档与保留段 192.0.2.0/24 / 198.51.100.0/24 / 203.0.113.0/24 / 240.0.0.0/4。
	if v4 := a.As4(); isReservedV4(v4) {
		return false
	}
	// IPv6 转换地址内嵌私网 IPv4 的绕过：6to4(2002::/16)、Teredro(2001::/32)、NAT64(64:ff9b::/96)。
	if v4, ok := embeddedV4(a); ok && !IsPublicAddr(v4) {
		return false
	}
	return true
}

// isCGNAT 判断是否落在 100.64.0.0/10。
func isCGNAT(v4 [4]byte) bool {
	return v4[0] == 100 && v4[1] >= 64 && v4[1] <= 127
}

// isReservedV4 判断是否落在保留/文档段。
func isReservedV4(v4 [4]byte) bool {
	switch {
	case v4[0] == 192 && v4[1] == 0 && v4[2] == 0: // 192.0.0.0/24 IETF 协议保留
		return true
	case v4[0] == 192 && v4[1] == 0 && v4[2] == 2: // TEST-NET-1
		return true
	case v4[0] == 198 && (v4[1] == 51 && v4[2] == 100 || v4[1] == 18 && v4[2] == 19): // TEST-NET-2 / 基准测试
		return true
	case v4[0] == 203 && v4[1] == 0 && v4[2] == 113: // TEST-NET-3
		return true
	case v4[0] >= 240: // 240.0.0.0/4 保留，含 255.255.255.255
		return true
	default:
		return false
	}
}

// embeddedV4 从 IPv6 转换地址中提取内嵌的 IPv4。
func embeddedV4(a netip.Addr) (netip.Addr, bool) {
	b := a.As16()
	switch {
	// 6to4: 2002::/16，第 3-4 字节为内嵌 IPv4。
	case a.Is4In6() || (b[0] == 0x20 && b[1] == 0x02):
		return netip.AddrFrom4([4]byte{b[2], b[3], b[4], b[5]}), true
	// Teredo: 2001:0000::/32，末 4 字节为取反后的 IPv4。
	case b[0] == 0x20 && b[1] == 0x01 && b[2] == 0x00 && b[3] == 0x00:
		return netip.AddrFrom4([4]byte{^b[12], ^b[13], ^b[14], ^b[15]}), true
	// NAT64: 64:ff9b::/96，第 12-15 字节为内嵌 IPv4。
	case b[0] == 0x00 && b[1] == 0x64 && b[2] == 0xff && b[3] == 0x9b:
		return netip.AddrFrom4([4]byte{b[12], b[13], b[14], b[15]}), true
	default:
		return netip.Addr{}, false
	}
}
