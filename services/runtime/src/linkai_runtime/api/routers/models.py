"""模型列表路由——契约 `service-api.yaml` GET /v1/models（透传 model-proxy 元数据）。"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter

from linkai_runtime.api.deps import CallerDep, ContainerDep
from linkai_runtime.api.schemas import ModelListOut, ModelOut, PriceOut

router = APIRouter(prefix="/v1", tags=["Models"])


@router.get(
    "/models",
    response_model=ModelListOut,
    summary="可调用模型列表（元数据：编码/能力/价格/上下文长度）",
    operation_id="listModels",
)
async def list_models(caller: CallerDep, container: ContainerDep) -> ModelListOut:
    cards = await container.gateway.list_models(caller.tenant_id)
    return ModelListOut(data=[_to_model_out(card) for card in cards])


def _to_model_out(card: Mapping[str, object]) -> ModelOut:
    price_raw = card.get("price")
    price: PriceOut | None = None
    if isinstance(price_raw, Mapping):
        price = PriceOut(
            inputPer1k=_as_float(price_raw.get("inputPer1k")),
            outputPer1k=_as_float(price_raw.get("outputPer1k")),
            creditPerCall=_as_int(price_raw.get("creditPerCall")),
        )
    capabilities_raw = card.get("capabilities")
    capabilities = (
        [str(c) for c in capabilities_raw if isinstance(c, str)]
        if isinstance(capabilities_raw, list)
        else []
    )
    provider_raw = card.get("provider")
    enabled_raw = card.get("enabled")
    return ModelOut(
        code=str(card.get("code", "")),
        name=str(card.get("name", "")),
        capabilities=capabilities,
        provider=provider_raw if isinstance(provider_raw, str) else None,
        contextLength=_as_int(card.get("contextLength")),
        price=price,
        enabled=enabled_raw if isinstance(enabled_raw, bool) else None,
    )


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
