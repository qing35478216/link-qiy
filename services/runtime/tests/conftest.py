"""共享测试夹具。

- 内存/脚本化端口（ScriptedGateway、内存仓储）——service 层单测
- SQLite 文件/内存库 + 组装容器——api 层契约用例
- respx mock model-proxy HTTP——integration 端到端
- socket 级禁网兜底（同 model-proxy：漏 mock 立刻炸，不打到真实服务）
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from linkai_runtime.api.deps import AppContainer
from linkai_runtime.domain.app_profile import AppProfile
from linkai_runtime.domain.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Choice,
    FinishReason,
    MessageRole,
    StreamDelta,
    TokenUsage,
)
from linkai_runtime.domain.errors import DomainError, ModelUpstreamError
from linkai_runtime.domain.ports import InvocationContext, TenantIdentity
from linkai_runtime.infra.api_key_store import DbApiKeyResolver, seed_dev_api_keys
from linkai_runtime.infra.app_profile_provider import StaticAppProfileProvider
from linkai_runtime.infra.config import Settings
from linkai_runtime.infra.conversation_repo import SqlAlchemyConversationRepository
from linkai_runtime.infra.db import Base
from linkai_runtime.infra.memory import NoopKnowledgeRetriever
from linkai_runtime.infra.model_proxy_client import HttpModelGateway
from linkai_runtime.infra.models import (  # noqa: F401  # 注册 ORM
    ApiKeyModel,
    ConversationModel,
    ExecutionTraceModel,
    MessageModel,
)
from linkai_runtime.infra.quota_guard import InMemoryQuotaGuard
from linkai_runtime.infra.trace_repo import SqlAlchemyExecutionTraceRepository
from linkai_runtime.services.chat_service import ChatService

TENANT = "t-001"
OTHER_TENANT = "t-002"
API_KEY = "sk-linkai-test-0001"
OTHER_API_KEY = "sk-linkai-test-0002"

#: 测试用应用设定（platform AppConfigOut 同构 camelCase）
DEMO_APP_CONFIG: dict[str, object] = {
    "basic": {"welcomeMessage": "你好，欢迎咨询", "guideQuestions": ["怎么退款？", "营业时间？"]},
    "modelPrompt": {
        "modelCode": "deepseek-chat",
        "systemPrompt": "你是{{role}}助手，回答不超过{{max_len}}字。",
        "temperature": 0.7,
        "memoryRounds": 3,
        "contextLength": 4096,
        "maxTokens": 512,
        "variables": [
            {"name": "role", "value": "客服"},
            {"name": "max_len", "value": "200"},
        ],
    },
    "knowledge": {
        "datasetIds": ["ds-1"],
        "missStrategy": "fallback",
        "missMessage": "知识库暂无相关内容，请转人工。",
    },
    "plugins": {"pluginIds": [], "execStrategy": "knowledge_first"},
    "advanced": {"rateLimitQpm": 60},
}

#: 上下文很紧的应用（验证预算截断）
TINY_APP_CONFIG: dict[str, object] = {
    "modelPrompt": {
        "modelCode": "deepseek-chat",
        "systemPrompt": "简短回答。",
        "memoryRounds": 5,
        "contextLength": 120,
        "maxTokens": 100,
    },
}


def make_settings(**overrides: object) -> Settings:
    """测试 Settings（SQLite 内存库；static 应用设定源）。"""
    base: dict[str, Any] = {
        "service_name": "runtime-test",
        "port": 0,
        "log_level": "warning",
        "database_url": "sqlite+pysqlite:///:memory:",
        "model_proxy_base_url": "http://model-proxy.test",
        "platform_base_url": "http://platform.test",
        "service_token": None,
        "app_profile_source": "static",
        "static_app_profiles_json": "",
        "dev_api_keys": "",
        "quota_default_daily_tokens": 1_000_000,
        "quota_tenant_daily_tokens_json": "",
        "http_timeout_seconds": 5.0,
        "http_connect_timeout_seconds": 1.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


class ScriptedGateway:
    """可编排的假模型网关（service/api 层用；integration 用真 HTTP + respx）。"""

    def __init__(
        self,
        *,
        chunks: tuple[str, ...] = ("你", "好", "世界"),
        prompt_tokens: int = 120,
        completion_tokens: int = 30,
        credits: int = 7,
        finish_reason: FinishReason = FinishReason.STOP,
        error: DomainError | None = None,
        error_at_chunk: int | None = None,
        delay_before_first_chunk: float = 0.0,
        response_id: str = "cmpl-test-0001",
        models: list[dict[str, object]] | None = None,
    ) -> None:
        self._chunks = chunks
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._credits = credits
        self._finish_reason = finish_reason
        self._error = error
        self._error_at_chunk = error_at_chunk
        self._delay = delay_before_first_chunk
        self._response_id = response_id
        self._models = models or [
            {
                "code": "deepseek-chat",
                "name": "DeepSeek Chat",
                "capabilities": ["chat"],
                "contextLength": 65536,
            }
        ]
        self.calls: list[tuple[str, ChatRequest, InvocationContext]] = []

    async def complete(self, request: ChatRequest, ctx: InvocationContext) -> ChatResponse:
        self.calls.append(("complete", request, ctx))
        if self._error is not None:
            raise self._error
        return ChatResponse(
            id=self._response_id,
            created=1_700_000_000,
            model=request.model,
            choices=(
                Choice(
                    index=0,
                    message=ChatMessage(role=MessageRole.ASSISTANT, content="".join(self._chunks)),
                    finish_reason=self._finish_reason,
                ),
            ),
            usage=TokenUsage.of(
                self._prompt_tokens, self._completion_tokens, credits=self._credits
            ),
        )

    async def stream(
        self, request: ChatRequest, ctx: InvocationContext
    ) -> AsyncIterator[StreamDelta]:
        self.calls.append(("stream", request, ctx))
        if self._delay > 0:
            import asyncio

            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        for index, chunk in enumerate(self._chunks):
            if self._error_at_chunk is not None and index == self._error_at_chunk:
                raise ModelUpstreamError("脚本化中断：连接中断")
            yield StreamDelta(delta=chunk, seq=index)
        yield StreamDelta(
            delta="",
            seq=len(self._chunks),
            finish_reason=self._finish_reason,
            usage=TokenUsage.of(
                self._prompt_tokens, self._completion_tokens, credits=self._credits
            ),
        )

    async def list_models(self, tenant_id: str) -> list[dict[str, object]]:
        return list(self._models)


def make_chat_service(
    *,
    gateway: ScriptedGateway,
    profiles: dict[str, dict[str, object]] | None = None,
    quota: InMemoryQuotaGuard | None = None,
) -> tuple[ChatService, sessionmaker]:
    """内存库 + 脚本化网关的 ChatService（service 层单测用）。"""
    factory = make_session_factory()
    profile_provider = StaticAppProfileProvider(profiles or {})
    service = ChatService(
        conversations=SqlAlchemyConversationRepository(factory),
        traces=SqlAlchemyExecutionTraceRepository(factory),
        profiles=profile_provider,
        gateway=gateway,  # type: ignore[arg-type]
        quota=quota or InMemoryQuotaGuard(default_daily_tokens=1_000_000),
        knowledge=NoopKnowledgeRetriever(),
    )
    return service, factory


def make_container(
    *,
    gateway: ScriptedGateway | HttpModelGateway,
    profiles: dict[str, dict[str, object]] | None = None,
    quota: InMemoryQuotaGuard | None = None,
    settings: Settings | None = None,
    seed_keys: tuple[str, ...] = (API_KEY,),
    tenant_ids: tuple[str, ...] = (TENANT,),
) -> AppContainer:
    """组装测试容器（SQLite 内存库 + 注入网关/应用设定/配额）。"""
    cfg = settings or make_settings()
    factory = make_session_factory()
    profile_provider = StaticAppProfileProvider(profiles or {})
    if seed_keys:
        seed_dev_api_keys(
            factory,
            ",".join(f"{key}:{tenant}" for key, tenant in zip(seed_keys, tenant_ids, strict=False)),
        )
    gateway_any: Any = gateway
    return AppContainer(
        settings=cfg,
        session_factory=factory,
        api_keys=DbApiKeyResolver(factory),
        gateway=gateway_any,
        profiles=profile_provider,
        chat_service=ChatService(
            conversations=SqlAlchemyConversationRepository(factory),
            traces=SqlAlchemyExecutionTraceRepository(factory),
            profiles=profile_provider,
            gateway=gateway_any,
            quota=quota or InMemoryQuotaGuard(default_daily_tokens=1_000_000),
            knowledge=NoopKnowledgeRetriever(),
        ),
    )


def make_client(container: AppContainer) -> TestClient:
    """预置容器的 TestClient（lifespan 检测到已装配即跳过自建）。"""
    from linkai_runtime.api.app import create_app

    app = create_app(container)
    return TestClient(app)


@pytest.fixture
def scripted_gateway() -> ScriptedGateway:
    return ScriptedGateway()


@pytest.fixture
def demo_container(scripted_gateway: ScriptedGateway) -> AppContainer:
    return make_container(
        gateway=scripted_gateway,
        profiles={"demo": DEMO_APP_CONFIG},
    )


@pytest.fixture
def demo_client(demo_container: AppContainer) -> TestClient:
    return make_client(demo_container)


@pytest.fixture
def raw_client(scripted_gateway: ScriptedGateway) -> TestClient:
    """无应用设定的直通模式客户端。"""
    return make_client(make_container(gateway=scripted_gateway))


@pytest.fixture
def identity() -> Any:

    return TenantIdentity(tenant_id=TENANT, user_id="u-001", key_id="k-001")


@pytest.fixture
def app_profile() -> AppProfile:
    return AppProfile.from_platform_config(app_code="demo", config=DEMO_APP_CONFIG)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """socket 级禁网兜底：漏 mock 的出网立刻失败（respx mock 仍然生效）。"""

    def _blocked(self: socket.socket, *args: object, **kwargs: object) -> None:
        raise AssertionError(f"测试中禁止真实出网（目标 {args[:2]}）——请用 respx mock 回放")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)


@pytest.fixture(autouse=True)
def _init_logging() -> None:
    from linkai_runtime.infra.logging import setup_logging

    setup_logging("runtime-test", "warning")


def auth_headers(key: str = API_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}
