package ssrf

import (
	"context"
	"testing"
)

// TestRuleSetAlignmentWithModelProxy 锁定 Go 侧与 model-proxy 侧 SSRF 规则的等价性。
//
// 背景（T-005 对齐）：两侧各有一套独立的出网闸门。若网段表漂移，
// 会出现「Python 阻断但 Go 放行」或反之的诡异 bug——同一目标地址
// 在不同服务得到不同结论，排查成本极高且难以复现。
//
// 本用例把 model-proxy 的 _BLOCKED_NETWORKS 与 BLOCKED_HOSTS 逐条镜像过来。
// 任何一侧改网段表，本用例即失败，强制两边同步。
//
// 修改方法：改 Go 侧规则时同步更新下面的表，并知会 ai-framework
// 更新 services/model-proxy/src/linkai_model_proxy/infra/ssrf.py。
func TestRuleSetAlignmentWithModelProxy(t *testing.T) {
	t.Parallel()

	cases := []struct {
		host string
		why  string
	}{
		// ---- model-proxy _BLOCKED_NETWORKS 逐条镜像 ----
		{host: "127.0.0.1", why: "127.0.0.0/8 回环"},
		{host: "10.1.2.3", why: "10.0.0.0/8 私有"},
		{host: "172.16.5.5", why: "172.16.0.0/12 私有"},
		{host: "172.31.255.255", why: "172.16.0.0/12 上界"},
		{host: "192.168.1.1", why: "192.168.0.0/16 私有"},
		{host: "169.254.169.254", why: "169.254.0.0/16 链路本地（云元数据）"},
		{host: "0.0.0.0", why: "0.0.0.0/8 未指定"},
		{host: "100.64.0.1", why: "100.64.0.0/10 CGNAT"},
		{host: "192.0.0.5", why: "192.0.0.0/24 IETF 协议保留"},
		// 这三条曾是真实分歧：Go 侧把 198.18.0.0/15 误写成 198.18/19，
		// 导致 198.19.x.x 段从网关侧漏放（T-005 对齐时发现）。
		{host: "198.18.0.1", why: "198.18.0.0/15 基准测试网"},
		{host: "198.19.255.255", why: "198.18.0.0/15 上界"},
		{host: "224.0.0.1", why: "224.0.0.0/4 组播"},
		{host: "239.1.1.1", why: "224.0.0.0/4 组播上界"},
		{host: "240.0.0.1", why: "240.0.0.0/4 保留"},
		{host: "255.255.255.255", why: "广播地址"},
		{host: "::1", why: "::1/128 回环"},
		{host: "fc00::1", why: "fc00::/7 ULA"},
		{host: "fd12::1", why: "fd00::/8 ULA"},
		{host: "fe80::1", why: "fe80::/10 链路本地"},

		// ---- model-proxy BLOCKED_HOSTS 逐条镜像 ----
		{host: "metadata.google.internal", why: "GCP 元数据主机名"},
		{host: "metadata.goog", why: "GCP 元数据主机名"},
		{host: "100.100.100.200", why: "阿里云元数据端点"},
		{host: "instance-data.ec2.internal", why: "EC2 元数据主机名"},
		{host: "localhost", why: "本机"},
	}

	for _, tc := range cases {
		t.Run(tc.host, func(t *testing.T) {
			t.Parallel()
			// IP 字面量走内建判定；主机名走黑名单。
			g := New(WithResolver(&fakeResolver{}))
			if _, err := g.Validate(context.Background(), "http://"+tc.host+"/"); err == nil {
				t.Errorf("Go 侧放行了 %s（%s），与 model-proxy 规则不一致——两侧必须同步",
					tc.host, tc.why)
			}
		})
	}
}

// TestGoSideIsStricterOrEqual 确认 Go 侧不会比 model-proxy 更宽松。
//
// 方向性要求：Go 侧作为"第二道防线"，可以更严（多阻断一些），
// 但不能更松（少阻断）。此用例锁住若干 Python 侧未覆盖、
// 但 Go 侧已覆盖的绕过手法，防止后续"简化"时被误删。
func TestGoSideIsStricterOrEqual(t *testing.T) {
	t.Parallel()

	// Python 侧规则表未覆盖、但 Go 侧额外阻断的绕过手法。
	goOnly := []struct {
		host string
		why  string
	}{
		{"2002:0a00:0001::1", "6to4 内嵌 10.x 私网"},
		{"64:ff9b::a9fe:a9fe", "NAT64 内嵌 169.254.169.254"},
		{"192.0.2.1", "TEST-NET-1 文档段"},
		{"198.51.100.1", "TEST-NET-2 文档段"},
		{"203.0.113.1", "TEST-NET-3 文档段"},
	}
	for _, tc := range goOnly {
		t.Run(tc.host, func(t *testing.T) {
			t.Parallel()
			g := New(WithResolver(&fakeResolver{}))
			if _, err := g.Validate(context.Background(), "http://["+tc.host+"]/"); err == nil {
				t.Errorf("Go 侧放行了 %s（%s）", tc.host, tc.why)
			}
		})
	}
}
