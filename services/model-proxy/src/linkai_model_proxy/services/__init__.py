"""应用层——业务编排与事务边界（依赖只准向内：api → services → domain）。

两件事：
1. `ModelGatewayService`：把领域编排包装成对外用例（Playground / 内部服务共用）；
2. `PlaygroundService`：提示词试玩——强制走网关，**不得**绕过计量。
"""

from linkai_model_proxy.services.gateway import ModelGatewayService
from linkai_model_proxy.services.playground import (
    PlaygroundRequest,
    PlaygroundResult,
    PlaygroundService,
)

__all__ = [
    "ModelGatewayService",
    "PlaygroundRequest",
    "PlaygroundResult",
    "PlaygroundService",
]
