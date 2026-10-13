# T-012 实现知识库文档导入管道（解析器注册）

## 关联
- 功能 ID：K-02（知识框架-文档导入+三档解析）
- 契约版本：contracts@openapi/console-api.yaml v0.3.0
- 负责角色：AI Framework Engineer

## 必读
- docs/03-开发实现框架设计.md 第 3.3 节（领域划分）
- docs/01-功能拆解蓝图.md 第 3.3 节（知识库）
- packages/contracts/openapi/console-api.yaml（Dataset/Document 部分）

## 文件领地
- services/knowledge/src/**（新增）
- packages/contracts/schemas/knowledge.yaml（如需扩展）

## 验收标准
1. 支持 pdf/docx/md/txt/单列csv 五种格式上传导入
2. 三种解析策略可切换：文本/增强（图文表格）/智能（图像识别，15积分/页）
3. 解析器走注册表模式（新增格式不准改管道内核）
4. 导入任务异步化（Celery knowledge 队列），进度可查询
5. 单测覆盖：每种格式一个用例 + 注册机制一个用例
6. 分段结果可预览（右侧窗口）

## Self-Check（完成前逐项确认）
- [ ] 只改了领地内文件
- [ ] domain 层无框架依赖
- [ ] 所有查询带 tenant_id
- [ ] ruff/black/mypy --strict 全过
- [ ] 单测通过且覆盖率达标
- [ ] 工单“交付说明”已填写

## 交付说明
（执行 agent 填写）
