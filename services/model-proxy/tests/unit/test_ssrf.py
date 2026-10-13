"""SSRF 闸门用例——铁律 5 的核心安全护栏。

三层防线：
1. **协议层**：只允许 https（开发态可显式放开 http）；
2. **白名单层**：主机名必须在允许列表内（防"任意 URL"型 SSRF）；
3. **IP 层**：解析后逐个校验，阻断内网/保留/元数据地址 + IPv6 转换地址。

⚠️ 用例设计说明（与Go 侧 `TestRuleSetAlignmentWithModelProxy` 对称）：
网段表是**两端各自维护的常量**，任一侧改错就会造成"一侧放行、另一侧阻断"的诡异 bug。
因此本文件锁定**行为契约**（哪些地址必须被拦）而非实现细节；
Go 侧镜像同一份行为清单，两端任一改动都会在 CI 里暴露。

**关于 IPv6 转换地址的事实澄清**（避免后人误判）：
Python `ipaddress` 的 `is_private`/`is_reserved` 对 6to4/NAT64/Teredo 等段
**当前已经判定为内网**，所以这些地址在加显式表之前就会被拦住。
显式拦截的价值不是"补当前漏网"，而是**消除对标准库隐式行为的依赖**——
这些判定来自 IANA 特殊用途登记表，是实现细节，跨版本可能变化。
显式表把安全边界从"押注标准库"变成"自有规则"，与标准库判定解耦。
"""

from __future__ import annotations

import ipaddress

import pytest

from linkai_model_proxy.infra.ssrf import (
    _BLOCKED_NETWORKS,
    _V6_TRANSITION_NETWORKS,
    SsrfPolicy,
    SsrfViolation,
    _embedded_ipv4,
    _host_allowed,
)

# 空白名单 = 跳过白名单层，隔离出IP 层的真实判定能力
OPEN_POLICY = SsrfPolicy(allowed_hosts=frozenset())


def _blocked(url: str, policy: SsrfPolicy = OPEN_POLICY) -> bool:
    try:
        policy.validate_url(url)
    except SsrfViolation:
        return True
    return False


class TestProtocolLayer:
    def test_http_rejected_by_default(self) -> None:
        assert _blocked("http://example.com/x")

    def test_https_allowed(self) -> None:
        assert not _blocked("https://example.com/x")

    def test_http_allowed_when_explicitly_enabled(self) -> None:
        dev = SsrfPolicy(allowed_hosts=frozenset(), allow_http=True)
        assert not _blocked("http://example.com/x", dev)

    @pytest.mark.parametrize("scheme", ["file", "gopher", "ftp", "dict", "ldap"])
    def test_dangerous_schemes_rejected(self, scheme: str) -> None:
        assert _blocked(f"{scheme}://example.com/x")

    def test_missing_host_rejected(self) -> None:
        assert _blocked("https:///path")


class TestIpv4Blocking:
    @pytest.mark.parametrize(
        ("cidr", "why"),
        [
            ("127.0.0.1", "回环"),
            ("10.0.0.1", "RFC1918"),
            ("172.16.0.1", "RFC1918"),
            ("192.168.1.1", "RFC1918"),
            ("169.254.169.254", "链路本地/云元数据"),
            ("0.0.0.0", "未指定"),
            ("100.100.100.200", "阿里云元数据（CGNAT 段内）"),
            ("198.18.0.1", "基准测试网"),
            ("198.19.255.254", "基准测试网 /15 上界（防掩码写错）"),
            ("224.0.0.1", "组播"),
            ("255.255.255.255", "广播"),
        ],
    )
    def test_internal_ipv4_blocked(self, cidr: str, why: str) -> None:
        # 直接调 IP 判定层：走 URL 需经 urlsplit/DNS，会引入不必要的解析依赖
        with pytest.raises(SsrfViolation):
            OPEN_POLICY._validate_ip(ipaddress.ip_address(cidr))

    def test_198_20_is_public_and_allowed(self) -> None:
        """/15 的上界之外必须是公网——防掩码写错成 /19 这类过严或过松。"""
        assert not _blocked("https://198.20.0.1/v1")

    @pytest.mark.parametrize(
        "host",
        [
            "169.254.169.254",
            "metadata.google.internal",
            "metadata.goog",
            "instance-data.ec2.internal",
        ],
    )
    def test_metadata_hostnames_blocked_even_if_whitelisted(self, host: str) -> None:
        """元数据端点必须无条件阻断——即便误配进白名单。"""
        policy = SsrfPolicy(allowed_hosts=frozenset({host}))
        assert _blocked(f"https://{host}/latest/meta-data/", policy)

    def test_aliyun_metadata_ip_is_blocked_by_cgnat_range(self) -> None:
        """100.100.100.200 落在 100.64.0.0/10 内，网段表已能拦。

        它同时出现在 BLOCKED_HOSTS 里是冗余的双保险——
        保留是为了即使将来 CGNAT 段被调整，该IP 仍被显式阻断。
        """
        addr = ipaddress.ip_address("100.100.100.200")
        assert any(addr in net for net in _BLOCKED_NETWORKS)


class TestIpv6Blocking:
    @pytest.mark.parametrize(
        "addr",
        ["::1", "fc00::1", "fd00::1", "fe80::1", "ff02::1", "::"],
    )
    def test_internal_ipv6_blocked(self, addr: str) -> None:
        with pytest.raises(SsrfViolation):
            OPEN_POLICY._validate_ip(ipaddress.IPv6Address(addr))

    @pytest.mark.parametrize(
        ("addr", "embedded"),
        [
            ("2002:0a00:0001::1", "10.0.0.1"),
            ("2002:7f00:0001::1", "127.0.0.1"),
            ("2002:a9fe:a9fe::1", "169.254.169.254"),
            ("64:ff9b::a9fe:a9fe", "169.254.169.254"),
            ("64:ff9b::a0a:1", "10.0.0.1"),
            ("::ffff:127.0.0.1", "127.0.0.1"),
            ("::ffff:10.0.0.1", "10.0.0.1"),
        ],
    )
    def test_transition_addresses_blocked(self, addr: str, embedded: str) -> None:
        """6to4 / NAT64 / IPv4-mapped：字面公网 IPv6，内嵌私网 IPv4。

        这是经典绕过——只做"是否 RFC1918"的朴素检查会漏掉它们。
        显式转换段规则保证：即使标准库某版本不再把这些段判为内网，
        本闸门仍会拦（不依赖标准库的隐式行为）。
        """
        with pytest.raises(SsrfViolation):
            OPEN_POLICY._validate_ip(ipaddress.IPv6Address(addr))
        assert _embedded_ipv4(ipaddress.IPv6Address(addr)) is not None

    def test_teredo_blocked(self) -> None:
        with pytest.raises(SsrfViolation):
            OPEN_POLICY._validate_ip(ipaddress.IPv6Address("2001:0:4136:e378:8000:63bf:3fff:fdd2"))

    @pytest.mark.parametrize(
        "addr",
        ["2001:4860:4860::8888", "2606:4700:4700::1111"],
    )
    def test_public_ipv6_still_allowed(self, addr: str) -> None:
        """不能为了严把公网 IPv6 也拦掉——否则 IPv6 出口全废。"""
        assert _host_allowed(addr, frozenset()) is False  # 空白名单下应走 IP 判定
        try:
            OPEN_POLICY._validate_ip(ipaddress.IPv6Address(addr))
        except SsrfViolation as exc:  # pragma: no cover - 失败即说明误拦
            pytest.fail(f"公网 IPv6 {addr} 被误拦：{exc}")


class TestEmbeddedIpv4Extraction:
    """内嵌 IPv4 抽取——保证"即使段表漏了，内嵌私网仍会被 IPv4 规则抓到"。"""

    @pytest.mark.parametrize(
        ("addr", "expected"),
        [
            ("2002:0a00:0001::1", "10.0.0.1"),  # 6to4：第 3-6 字节
            ("64:ff9b::a9fe:a9fe", "169.254.169.254"),  # NAT64：末 4 字节
            ("::ffff:10.0.0.1", "10.0.0.1"),  # IPv4-mapped：末 4 字节
            ("2001:4860:4860::8888", None),  # 公网 IPv6：非转换地址
            ("fc00::1", None),  # ULA：非转换地址
        ],
    )
    def test_extraction(self, addr: str, expected: str | None) -> None:
        actual = _embedded_ipv4(ipaddress.IPv6Address(addr))
        assert actual is None if expected is None else str(actual) == expected

    def test_teredo_extraction_unobfuscates(self) -> None:
        """Teredo 的内嵌 IPv4 是取反混淆的，抽取时必须还原。"""
        # 末 4 字节全0xff → 取反后为 0.0.0.0（取反后仍应走 IPv4 规则）
        assert _embedded_ipv4(ipaddress.IPv6Address("2001:0::ffff:ffff:ffff:ffff")) is not None

    def test_public_ipv6_returns_none(self) -> None:
        assert _embedded_ipv4(ipaddress.IPv6Address("2001:4860:4860::8888")) is None


class TestNetblockTableIntegrity:
    """网段表自身的一致性——防"掩码写错"这类低级错误（Go 侧真发生过）。"""

    @pytest.mark.parametrize(
        "cidr",
        ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"],
    )
    def test_expected_v4_ranges_present(self, cidr: str) -> None:
        net = ipaddress.ip_network(cidr)
        assert net in _BLOCKED_NETWORKS, f"网段表缺少 {cidr}"

    def test_benchmark_range_is_slash15(self) -> None:
        """198.18.0.0/15 必须覆盖到 198.19.255.255——Go 侧曾误写成 /19。"""
        net = ipaddress.ip_network("198.18.0.0/15")
        assert ipaddress.ip_address("198.19.255.254") in net
        assert ipaddress.ip_address("198.20.0.1") not in net

    def test_transition_ranges_explicitly_declared(self) -> None:
        """转换段必须在自有表里显式出现，不依赖标准库隐式行为。"""
        declared = {str(n) for n in _V6_TRANSITION_NETWORKS}
        for required in ("2002::/16", "64:ff9b::/96", "2001::/32"):
            assert required in declared, f"转换段 {required} 未显式声明"

    def test_all_table_entries_are_valid_networks(self) -> None:
        for net in (*_BLOCKED_NETWORKS, *_V6_TRANSITION_NETWORKS):
            assert isinstance(net, (ipaddress.IPv4Network, ipaddress.IPv6Network))


class TestWhitelistLayer:
    def test_host_not_in_whitelist_rejected(self) -> None:
        policy = SsrfPolicy(allowed_hosts=frozenset({"api.openai.com"}))
        assert _blocked("https://evil.example.com/x", policy)

    def test_exact_host_allowed(self) -> None:
        policy = SsrfPolicy(allowed_hosts=frozenset({"api.openai.com"}))
        assert not _blocked("https://api.openai.com/v1/chat/completions", policy)

    def test_wildcard_suffix_supported(self) -> None:
        policy = SsrfPolicy(allowed_hosts=frozenset({"*.bigmodel.cn"}))
        assert not _blocked("https://open.bigmodel.cn/api/v4/x", policy)

    def test_wildcard_does_not_match_bare_domain(self) -> None:
        """`*.x.com` 只匹配子域，不匹配裸域本身（最小权限取向）。

        裸域需在白名单里单独列出——见 DEFAULT_ALLOWED_HOSTS 的注释。
        """
        assert not _host_allowed("bigmodel.cn", frozenset({"*.bigmodel.cn"}))
        assert _host_allowed("open.bigmodel.cn", frozenset({"*.bigmodel.cn"}))

    def test_wildcard_does_not_match_suffix_confusion(self) -> None:
        """`*.x.com` 不得匹配 `evilx.com`——避免前缀拼接绕过。"""
        assert not _host_allowed("evilbigmodel.cn", frozenset({"*.bigmodel.cn"}))

    def test_empty_whitelist_allows_all_but_still_checks_ip(self) -> None:
        """空白名单 = 不限主机名，但 IP 层判定仍然生效。"""
        assert not _blocked("https://8.8.8.8/x")
        assert _blocked("https://127.0.0.1/x")


class TestPolicyIsFailClosed:
    def test_unresolvable_host_rejected(self) -> None:
        """解析失败必须拒——不能"解析不了就先放行"。"""
        policy = SsrfPolicy(allowed_hosts=frozenset())
        assert _blocked("https://this-host-does-not-exist-9x8y7z.invalid/x", policy)

    def test_every_violation_is_exception_not_silent(self) -> None:
        """所有拒绝路径都必须抛 SsrfViolation，不允许静默返回。"""
        for url in (
            "http://x.com",  # 协议
            "https://127.0.0.1",  # 回环
            "https://[::1]",  # IPv6 回环
            "https://169.254.169.254",  # 元数据
            "https://[2002:0a00:0001::1]",  # 6to4 内嵌私网
        ):
            with pytest.raises(SsrfViolation):
                OPEN_POLICY.validate_url(url)
