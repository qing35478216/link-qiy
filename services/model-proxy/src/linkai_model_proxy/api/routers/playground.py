"""Playground 路由——控制台侧模型试玩。

⚠️ 契约说明：契约 `console-api.yaml` v0.1.1 **没有** Playground 端点。
按铁律 1（契约先行、契约只由 Contract Engineer 改），本工单**不擅自改契约**，
先用内部路由 `/_internal/playground` 提供能力，路径前缀即表明其非对外契约面。
契约缺口已上报 T-015，待v0.2 补`POST /playground/completions`。

计量：Playground 内部走 `ModelGatewayService`，与其他调用路径完全一致，
因此与业务调用一样产生 MeteringEvent、消耗租户积分。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from linkai_model_proxy.api.auth import CallerIdentity, resolve_caller
from linkai_model_proxy.api.dependencies import AppContainer, get_container
from linkai_model_proxy.api.schemas import (
    PlaygroundRequestIn,
    PlaygroundResponseOut,
    UsageOut,
)
from linkai_model_proxy.domain.errors import DomainError
from linkai_model_proxy.services.playground import PlaygroundRequest

router = APIRouter(prefix="/_internal/playground", tags=["Playground"])


@router.post(
    "/completions",
    response_model=PlaygroundResponseOut,
    summary="模型试玩（Playground）",
    operation_id="playgroundComplete",
)
async def playground_complete(
    payload: PlaygroundRequestIn,
    caller: Annotated[CallerIdentity, Depends(resolve_caller)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> PlaygroundResponseOut:
    """执行一次试玩。计量与业务调用一致。"""
    try:
        request = PlaygroundRequest(
            model=payload.model_,
            prompt=payload.prompt,
            system=payload.system,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_PLAYGROUND_REQUEST", "message": str(exc)},
        ) from exc

    try:
        result = await container.playground.play(request, caller.to_context())
    except DomainError as exc:
        # 4xx语义错误向上游映射为 4xx，可重试错误映射为 502
        http_status = status.HTTP_502_BAD_GATEWAY if exc.retriable else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=http_status,
            detail={"code": exc.code, "message": str(exc), "retriable": exc.retriable},
        ) from exc

    return PlaygroundResponseOut(
        model=result.model,
        content=result.content,
        usage=UsageOut(
            promptTokens=result.prompt_tokens,
            completionTokens=result.completion_tokens,
            totalTokens=result.total_tokens,
            credits=result.credits,
        ),
        finish_reason=result.finish_reason,
    )


@router.get(
    "/models",
    summary="可试玩模型列表",
    operation_id="listPlaygroundModels",
)
async def list_playground_models(
    caller: Annotated[CallerIdentity, Depends(resolve_caller)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    """给控制台 Playground 侧栏填充模型下拉。"""
    return {"data": container.playground.suggest_models(caller.tenant_id)}
