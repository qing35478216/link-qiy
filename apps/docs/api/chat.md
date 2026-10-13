# 对话接口

::: warning 骨架阶段
请求/响应结构以 `packages/contracts/openapi/console-api.yaml`（T-001 冻结）为准，本文档在契约冻结后自动生成。
:::

## POST /v1/chat/completions

OpenAI 兼容的对话接口。应用级调用需携带应用 code 与 API Key。

```bash
curl -X POST https://api.link-ai.tech/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -d '{"app_code": "<APP_CODE>", "messages": [{"role": "user", "content": "你好"}]}'
```

## 计费

对话按模型 token 消耗积分，标准版及以上开放高级 API 能力。详见[定价](https://link-ai.tech/price/)。
