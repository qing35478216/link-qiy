## HANDOFF: T-012 → T-013
- 状态：DONE / BLOCKED / NEEDS-HUMAN
- 产出：分支 feat/T-012-knowledge-import，PR #47
- 验证：单测 23 passed；契约测试通过；lint/mypy 通过
- 下游注意：Dataset API 新增了 parse_strategy 字段（v0.3.0），前端画布需同步
- 风险：智能解析依赖图像识别模型，成本待评估
