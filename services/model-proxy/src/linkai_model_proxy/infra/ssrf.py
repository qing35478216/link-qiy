"""出网闸门——**铁律 5：所有外部请求必须过ssrf-proxy / SSRF 校验**。

model-proxy 调用厂商 API 是最典型的外部请求场景：URL 来自租户配置
（自定义模型的 base_url）或模型目录，因此**默认不可信**。网关必须做到：

1. 仅允许 https（开发态可显式放开 http）；
2. 阻断内网地址（回环 / RFC1918 / 链路本地 / 元数据服务 169.254.169.254 等）；
3. 主机名解析后再校验 IP（防DNS rebinding 的第一层）；
4. **不跟随重定向**（重定向到内网是经典绕过手法）；
5. 目标主机需在白名单内（`allowed_hosts`）——厂商 base_url 由平台配置而非租户任意指定；
6. 超时与响应体大小上限，防资源耗尽。

配置来源：`SsrfPolicy`，由环境变量注入（infra/settings.py）。
本模块**只做校验决策**，不发起连接——校验通过后由 `http_client.py` 用固定 IP + Host 头建连。
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# 云厂商元数据端点：即使被当作公网 IP 也必须阻断
BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS/GCP/Azure/OpenStack 统一元数据
        "metadata.google.internal",
        "metadata.goog",
        "100.100.100.200",  # 阿里云元数据
        "instance-data.ec2.internal",
    }
)

# 不允许的网段：回环 / 私有 / 链路本地 / 组播 / 保留 / 未指定
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),  # 基准测试网
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA
    ipaddress.ip_network("fe80::/10"),  # 链路本地
)


class SsrfViolation(Exception):
    """SSRF 校验失败——**绝不**降级为放行。"""


@dataclass(frozen=True, slots=True)
class SsrfPolicy:
    """SSRF 策略。

    `allowed_hosts` 为空表示"不限制主机名，但仍做 IP 网段阻断"。
    生产环境**建议**显式列白名单（各厂商 API 域名）。
    """

    allowed_hosts: frozenset[str] = field(default_factory=frozenset)
    allow_http: bool = False
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 60.0
    max_response_bytes: int = 4 * 1024 * 1024  # 4MiB，防超大响应打爆内存
    max_redirects: int = 0  # 恒为 0：不跟随重定向

    def validate_url(self, url: str) -> tuple[str, int, str]:
        """校验 URL，返回 `(host, port, scheme)`。任何可疑形态都抛 `SsrfViolation`。"""
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        host = parts.hostname or ""

        if scheme not in ("https", "http"):
            raise SsrfViolation(f"协议 {scheme!r} 不允许（仅 https）")
        if scheme == "http" and not self.allow_http:
            raise SsrfViolation("http 不允许（仅 https）；开发态可显式放开")
        if not host:
            raise SsrfViolation("URL 缺少主机名")
        if host.lower() in BLOCKED_HOSTS:
            raise SsrfViolation(f"主机 {host!r} 是被阻断的元数据端点")

        if self.allowed_hosts and not _host_allowed(host, self.allowed_hosts):
            raise SsrfViolation(f"主机 {host!r} 不在白名单内")

        self._validate_resolved(host)

        default_port = 443 if scheme == "https" else 80
        port = parts.port or default_port
        return host, port, scheme

    def _validate_resolved(self, host: str) -> None:
        """解析主机名并逐个校验 IP——防"域名解析到内网"与 DNS rebinding 第一层。"""
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            addr = None

        if addr is not None:
            self._validate_ip(addr)
            return

        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise SsrfViolation(f"主机 {host!r} 解析失败：{exc}") from exc

        if not infos:
            raise SsrfViolation(f"主机 {host!r} 未解析到任何地址")

        for info in infos:
            raw_ip = info[4][0]
            try:
                self._validate_ip(ipaddress.ip_address(raw_ip))
            except ValueError as exc:  # pragma: no cover - getaddrinfo 理论上只返回合法 IP
                raise SsrfViolation(f"主机 {host!r} 解析出非法地址 {raw_ip!r}") from exc

    @staticmethod
    def _validate_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if addr.is_loopback:
            raise SsrfViolation(f"目标 {addr} 是回环地址")
        if addr.is_link_local:
            raise SsrfViolation(f"目标 {addr} 是链路本地地址")
        if addr.is_private or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            raise SsrfViolation(f"目标 {addr} 是内网/保留地址")
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise SsrfViolation(f"目标 {addr} 落在阻断网段 {net}")


def _host_allowed(host: str, allowed: frozenset[str]) -> bool:
    """白名单匹配：支持精确主机与 `*.suffix` 形式。"""
    lowered = host.lower()
    for entry in allowed:
        candidate = entry.lower()
        if candidate.startswith("*."):
            if lowered == candidate[2:] or lowered.endswith(candidate[1:]):
                return True
        elif lowered == candidate:
            return True
    return False
