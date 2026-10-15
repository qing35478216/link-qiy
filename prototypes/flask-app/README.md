# Flask 管理后台原型（LinkAI console 复刻）

**同步** Flask 管理后台，对齐 LinkAI 对标物（Dify）的 code 方式。
架构决策见 `infra/ADOPTED-TOOLS.md` 的 **ADR-002**（甲方指定，范围限定在本原型沙箱）。

## 跑起来

```bash
cd prototypes/flask-app
.venv/bin/python run.py
```

| 入口 | 地址 |
|------|------|
| 管理后台 | http://127.0.0.1:5001/ |
| Swagger UI | http://127.0.0.1:5001/doc |
| API spec | http://127.0.0.1:5001/api/swagger.json |

演示账号：`demo@linkai.local` / `demo123456`（也可自行注册）

依赖 PostgreSQL——本机 colima 容器 `linkai-postgres` 需在跑：
```bash
docker compose up -d postgres redis   # minio 镜像暂拉不到，见项目记忆
```

## 已实现（Phase 0 出口标准的前四步）

| 功能 | 路由 | 说明 |
|------|------|------|
| 登录 / 注册 / 登出 | `/auth/*` | flask-login session + werkzeug 哈希 |
| 应用工厂（列表） | `/console/factory` | 3 列卡片网格 + 创建弹窗（轻量/知识应用） |
| 创建应用 | `POST /console/factory/create` | 分配 **7 位随机 code**（LinkAI 风格，如 `Ix1xyUJ`） |
| 应用配置 | `/console/agent?code=X` | 基础信息 / 对话设置 / 模型设置 / 应用设定（提示词） |
| 调试对话 | `/console/agent/chat?code=X` | 原型期本地回显，未接真实模型 |
| RESTX API | `/api/console/apps` | 列表 + 创建 + 详情，中文不转义 |

安全：应用按 `owner_id` 归属校验，访问他人应用返回 404（不暴露存在性）。

## 目录结构

```
app/
├── __init__.py          # 应用工厂（注册扩展/蓝图/建表）
├── config.py            # 配置（DB 指向 colima 容器）
├── extensions.py        # db / login_manager / api 实例
├── codegen.py           # LinkAI 风格 7 位 code 生成器
├── models.py            # proto_users / proto_apps（SQLAlchemy）
├── blueprints/
│   ├── auth.py          # 登录注册
│   ├── pages.py         # 页面路由（Jinja2 SSR）
│   └── console_api.py   # RESTX API
├── services/app_service.py  # 创建/更新逻辑（路由只做 HTTP）
├── templates/           # base / login / register / factory / agent_config / agent_chat
└── static/style.css
```

## 与主仓的边界

- 表名带 `proto_` 前缀，不碰主仓 alembic 管理的 schema
- 不写 tenant_id / OTel / 四层架构（原型沙箱豁免）
- **验证满意后的落地路径**见 ADR-002「后续路径」一节

## 已知取舍（原型期故意从简）

- 对话调试为本地回显，未接 model-proxy
- 知识库 / 插件 / 限流 / 高级配置 Tab 未实现（界面占位）
- 无 CSRF 保护、无密码强度策略、无限流——正式实现必须补
- 建表用 `db.create_all()`，未引入 alembic
