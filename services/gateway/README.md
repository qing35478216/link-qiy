# services/gateway — API 网关 + 渠道网关（Go）

全站统一入口。**只做协议 / 连接 / 路由，不写任何业务或 AI 逻辑**——
业务在 Python 服务侧（铁律：Go 服务禁止出现业务规则与 AI 逻辑）。

领地：channel-engineer（07）。相关工单：T-008。

---

## 一、四个横切机制与「三角分离」

四件事各自独立成包、互不 import，可单独测试与替换：

| 机制 | 包 | 只回答 | 不关心 |
|---|---|---|---|
| 鉴权 | `internal/auth` | 这是谁 | 配额、路由、CORS |
| 限流 | `internal/ratelimit` | 超预算了吗 | 权限、路由、CORS |
| 路由 | `internal/routing` | 该去哪个后端 | 凭证、配额、CORS |
| CORS | `internal/cors` | 能不能跨域 | 身份、配额、路由 |

**分离的实现方式**：包之间零 import 依赖，靠 `internal/domain` 的
context 键约定传递数据（`Principal` 与 `Surface`）。
Go 的 context key 按类型比较，因此这两个键定义在**最内层的 domain 包**——
若 auth 与 ratelimit 各自定义未导出的同名类型，读取会永远失败。

### 处理链顺序（不可随意调整）

```
路由解析 ──→ CORS ──→ 鉴权 ──→ 限流 ──→ 路由转发
Resolve      CORS     Auth     Limit      Forward
```

| 位置 | 为什么必须在这里 |
|---|---|
| 路由解析 | 只匹配路由 + 标记入口面。不放在最前：无路由的请求不该消耗鉴权/限流配额 |
| CORS | **必须在鉴权之前**：OPTIONS 预检不携带凭证，先过鉴权则所有跨域预检 401 |
| 鉴权 | 确立 Principal 与租户 |
| 限流 | 依赖鉴权写入的 Principal 才能定租户配额 |
| 路由转发 | 依赖 Principal 注入租户头，并做 scope 校验 |

> 路由拆成「解析」与「转发」两段，是因为入口面必须在鉴权前可确定（CORS 的前提），
> 而转发必须看到 Principal（鉴权的产物）。一段做不到两件事。

---

## 二、CORS 三角分离

三组策略独立注册、独立求值，`internal/cors` 不 import 任何其他横切包。

| 入口面 | 用途 | 默认来源 | 凭证 |
|---|---|---|---|
| `console` | 控制台 API | 配置白名单 | 可开 |
| `service` | 开放 API（SDK） | 配置白名单 | 否 |
| `embed` | 网页嵌入（第三方 iframe） | `*` | **强制否** |

硬规则：`Allow-Origin: *` 与 `Allow-Credentials: true` **不得同时出现**，
违反则在 `NewPolicy` 构造期直接返回 error（导致启动失败），不产生危险策略。

---

## 三、多租户（铁律 6）

- `Principal.TenantID` 为空 → **一律拒绝**，不进入下游
- 客户端声明的 `X-Tenant-Id` 与凭证租户不符 → **403**（跨租户越权）
- 网关向下游注入 `X-Tenant-Id` / `X-Subject-Id`，下游只信任来自网关的该头
- 限流三个维度的限流键**都含租户**，一个租户打满不影响其他租户

---

## 四、SSRF 防护（铁律 5）

所有出站请求走 `internal/ssrf.Guard` 提供的 `http.Transport`，三层防御：

1. **URL 静态校验** —— scheme 仅 http/https；拒绝 userinfo；端口限 1-65535 且需在白名单
2. **DNS 解析后校验** —— 解析出的每一个 IP 都必须公网可路由（多 A 记录含一个内网即拒绝）
3. **连接时校验** —— 解析一次 → 校验 → **连字面 IP**，消除 DNS rebinding 的 TOCTOU 窗口

拦截范围：回环 / RFC1918 / 链路本地（含云元数据 `169.254.169.254`）/
CGNAT `100.64/10` / 组播 / 文档保留段 / IPv6 转换地址内嵌私网 IPv4（6to4、Teredro、NAT64）。

> ⚠️ 出站请求**不要用** `http.DefaultTransport`，否则 `HTTP_PROXY` 环境变量
> 会让请求绕过本守卫。`Guard.Transport()` 已显式 `Proxy: nil`。

---

## 五、运行

```bash
export GATEWAY_JWT_SECRET="$(openssl rand -base64 48)"   # 必填，≥32 字节
export GATEWAY_UPSTREAMS="platform=http://platform:8001=console;runtime=http://runtime:8002=service"
export GATEWAY_ROUTES="GET /console/api/v1/apps platform; POST /service/v1/chat runtime"
go run ./cmd/gateway
```

配置全部来自环境变量（不读配置文件，避免密钥落盘）。关键变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `GATEWAY_JWT_SECRET` | 无 | **必填**，HS256 签名密钥，≥32 字节 |
| `GATEWAY_JWT_ISSUER` | 空 | 非空则校验签发方 |
| `GATEWAY_TENANT_RATE` / `_WINDOW` | 1000 / 1m | 租户级限流，0 = 关闭该维度 |
| `GATEWAY_KEY_RATE` / `_WINDOW` | 200 / 1m | 凭证级限流 |
| `GATEWAY_ENDPOINT_RATE` / `_WINDOW` | 300 / 1m | 端点级限流 |
| `GATEWAY_CORS_CONSOLE_ORIGINS` | `http://localhost:5173` | 逗号分隔 |
| `GATEWAY_UPSTREAMS` | 无 | `name=target=surface[|scope1,scope2];...` |
| `GATEWAY_ROUTES` | 无 | `METHOD /prefix upstream; ...` |

健康检查：`/healthz`、`/readyz`（不经过任何横切机制，探针不受配额影响）。

---

## 六、扩展（铁律 4：适配器 + 注册表）

新增能力一律加适配器，不改内核：

| 需求 | 做法 |
|---|---|
| 新认证方式（OAuth2 / mTLS） | 实现 `auth.Authenticator` → `auth.Registry.Register` |
| 分布式限流（多实例） | 实现 `ratelimit.Limiter`（Redis 实现）替换进程内令牌桶 |
| 新后端服务 | `Table.RegisterUpstream` + `Table.RegisterRoute` |
| 新 CORS 入口面 | `cors.NewPolicy` + `Registry.Register` |

---

## 七、开发

```bash
golangci-lint run ./...        # 零告警为门禁
go test -race ./...            # 全过
go test -cover ./...           # 各包 ≥70%
```

改 `.golangci.yml` 后务必 `golangci-lint config verify`——
**位置写错时 golangci-lint 不报错，而是静默忽略排除规则**（v2 的
`exclusions` 与 `settings` 平级，同在 `linters` 下）。

开源选型的四项核查与候选对比表见 [`docs/选型对比.md`](docs/选型对比.md)。
