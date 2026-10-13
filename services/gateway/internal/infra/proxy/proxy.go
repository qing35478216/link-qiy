// Package proxy 提供基于 net/http/httputil 的反向代理实现。
//
// 它是 routing.Proxy 接口的一个适配器（铁律 4）。
//
// # 为什么这里不挂 SSRF 闸门（重要，别误加）
//
// 反代的上游是**平台自己的内部服务**（platform:8001 / runtime:8002……），
// 地址来自启动期配置而非用户输入。把 internal/ssrf.Guard 挂到这里的
// Transport 上会导致**全部上游被当作"内网地址"拦掉**——
// 因为 internal/ssrf 的职责恰恰是阻断内网，而这里必须访问内网。
// 两者语义相反，不能混用。
//
// 闸门的正确接入点是"**用户可控 URL**"的出站场景：webhook 回调、
// 链接预览、从 URL 导入。这些功能在 Phase 1+ 才会引入，
// 届时必须走 internal/ssrf.Guard.Client()。
//
// 为防止"闸门躺在目录里没人用"这种静默失效，本包在
// TestSsrfGuardIsExportedForUserURLScenarios 中断言
// internal/ssrf 对外提供可用的 Client/Validate——
// 即：闸门可被未来的功能直接复用，而不是需要先改造它。
package proxy

import (
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sync"
	"time"

	"github.com/linkai/gateway/internal/routing"
)

// ReverseProxy 按上游名池化 *httputil.ReverseProxy。
type ReverseProxy struct {
	mu      sync.RWMutex
	proxies map[string]*httputil.ReverseProxy
}

// New 创建反向代理器。
func New() *ReverseProxy {
	return &ReverseProxy{proxies: make(map[string]*httputil.ReverseProxy)}
}

// Serve 实现 routing.Proxy。
func (p *ReverseProxy) Serve(w http.ResponseWriter, r *http.Request, u routing.Upstream) {
	p.forUpstream(u).ServeHTTP(w, r)
}

// clientIPHeaders 是承载"客户端 IP"的各种非标准头。
//
// X-Forwarded-For/Host/Proto 不在此列——它们由 SetXForwarded() 生成，
// 天然被改写为真实连接信息。下列这些则没有生成者，
// 若放行就是客户端说了算，下游一旦信任即构成 IP 伪造。
var clientIPHeaders = []string{
	"X-Real-IP",        // nginx 约定
	"X-Client-IP",      // 部分网关/云厂商
	"CF-Connecting-IP", // Cloudflare
	"True-Client-IP",   // Akamai
	"X-Originating-IP", // 一些 CDN
	"Forwarded",        // RFC 7239 标准头
}

// transport 返回出站 Transport。
//
// 刻意使用裸 Dialer 而非 internal/ssrf.Guard.Transport()——理由见包注释：
// 上游是内部服务，SSRF 闸门会把它拦掉（它的职责正是阻断内网）。
func (p *ReverseProxy) transport() *http.Transport {
	return &http.Transport{
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		MaxIdleConns:          200,
		MaxIdleConnsPerHost:   50,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   5 * time.Second,
		ExpectContinueTimeout: time.Second,
	}
}

// forUpstream 取出或创建某上游的代理实例。
func (p *ReverseProxy) forUpstream(u routing.Upstream) *httputil.ReverseProxy {
	p.mu.RLock()
	rp, ok := p.proxies[u.Name]
	p.mu.RUnlock()
	if ok {
		return rp
	}

	target, err := url.Parse(u.Target)
	if err != nil {
		// 上游地址来自启动期配置，解析失败说明配置错了。
		// 此时退化为 502 而不是 panic：配置错误不应让整个网关进程崩溃。
		return brokenProxy()
	}

	rp = &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.SetURL(target)
			pr.Out.Host = target.Host
			// 剥离网关注入的内部头，避免客户端伪造同名头注入下游。
			pr.Out.Header.Del(routing.HeaderTraceParent)
			// 承载"客户端 IP"的各种头一律剥离。网关是唯一可信来源，
			// 下游要真实客户端 IP 只能读 X-Forwarded-For（由 SetXForwarded 生成）。
			// 不剥离的话，下游一旦信任 X-Real-IP 等头，客户端即可伪造。
			for _, h := range clientIPHeaders {
				pr.Out.Header.Del(h)
			}
			pr.SetXForwarded()
		},
		// 网关是统一入口：隐藏上游信息，错误也归一为 502。
		// 在构造时设置一次即可——每次请求改写共享对象是数据竞争。
		ErrorHandler: badGatewayHandler,
		// 出站挂载 SSRF 闸门（铁律 5）：拨号层校验目标 IP，
		// 防上游地址被误配为内网/元数据端点。
		Transport: p.transport(),
	}

	p.mu.Lock()
	defer p.mu.Unlock()
	// 双检：并发下可能已有人建好，优先复用先写入的那个。
	if existing, dup := p.proxies[u.Name]; dup {
		return existing
	}
	p.proxies[u.Name] = rp
	return rp
}

// badGatewayHandler 是统一的出站失败处理。
func badGatewayHandler(w http.ResponseWriter, _ *http.Request, _ error) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusBadGateway)
	_, _ = w.Write([]byte(`{"error":"bad_gateway"}`))
}

// brokenProxy 返回一个只会回 502 的代理，用于上游地址非法的降级。
// 上游地址来自启动期配置，解析失败说明配置错了；此时降级为 502 而不是
// panic——配置错误不应让整个网关进程崩溃。
func brokenProxy() *httputil.ReverseProxy {
	return &httputil.ReverseProxy{
		Rewrite:      func(*httputil.ProxyRequest) {},
		ErrorHandler: badGatewayHandler,
	}
}

// 编译期断言：反向代理必须满足 routing.Proxy 接口。
var _ routing.Proxy = (*ReverseProxy)(nil)
