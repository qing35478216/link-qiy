// Package proxy 提供基于 net/http/httputil 的反向代理实现。
//
// 它是 routing.Proxy 接口的一个适配器（铁律 4）。
// 转发目标的上游地址必须由路由注册表给出；本包不接受用户提供的 URL，
// 因此不需要（也不提供）SSRF 防护——出站到用户 URL 的场景请走 internal/ssrf。
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
			pr.SetXForwarded()
		},
		// 网关是统一入口：隐藏上游信息，错误也归一为 502。
		// 在构造时设置一次即可——每次请求改写共享对象是数据竞争。
		ErrorHandler: badGatewayHandler,
		Transport: &http.Transport{
			DialContext: (&net.Dialer{
				Timeout:   5 * time.Second,
				KeepAlive: 30 * time.Second,
			}).DialContext,
			MaxIdleConns:          200,
			MaxIdleConnsPerHost:   50,
			IdleConnTimeout:       90 * time.Second,
			TLSHandshakeTimeout:   5 * time.Second,
			ExpectContinueTimeout: time.Second,
		},
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
