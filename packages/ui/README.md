# packages/ui — 控制台基础组件库

60+ 基础组件，全站复用。设计 Token 见 docs/04 第二部分，首批 18 个组件见工单 T-011。

领地：控制台前端工程师（frontend-console）。

## 使用

```ts
import { LkAppPage, LkDataTable, LkQuotaBadge } from '@linkai/ui';
import '@linkai/ui/tokens.css'; // Design Token + Element Plus 主题变量对齐
```

## Design Token（docs/04 2.2，源码直消费）

| 类别 | 变量 | 值 |
|---|---|---|
| 主色 | `--lk-color-primary` | `#378ADD` |
| 成功/警告/危险 | `--lk-color-success/warning/danger` | `#1D9E75` / `#BA7517` / `#E24B4A` |
| 文本 | `--lk-text-primary/secondary/weak` | `#1F2328` / `#5F5E5A` / `#888780` |
| 背景 | `--lk-bg-page/card/hover` | `#F7F7F5` / `#FFFFFF` / `#F1EFE8` |
| 边框 | `--lk-border-color` | `#E5E3DC`（0.5px） |
| 圆角 | `--lk-radius-component/card/modal` | `8px` / `12px` / `16px` |
| 间距 | `--lk-space-1/2/3/4/6/8` | `4/8/12/16/24/32 px` |
| 字号 | `--lk-font-size-xs/sm/md/lg/xl` | `12/13/14/16/20 px` |

暗色模式：`[data-theme="dark"]` 下所有颜色变量换值，组件零改动。**组件内禁止硬编码 hex**。

## 首批 18 组件（docs/04 2.3）

| 组件 | 用途 | 关键状态 |
|---|---|---|
| `LkAppPage` | 页头+内容区骨架 | loading/error（含重试） |
| `LkDataTable` | 列表页表格（泛型行类型） | 空/加载中/分页/批量选择 |
| `LkFilterBar` | 筛选区 | 折叠/展开/重置 |
| `LkEmptyState` | 空状态 | 内置插图 + CTA 插槽 |
| `LkConfigSection` | 配置分区 | 脏标记圆点/折叠/禁用 |
| `LkPromptEditor` | 提示词编辑器 | 字符统计/变量插入/一键优化 |
| `LkModelSelector` | 模型下拉 | 搜索/能力标签/价格 |
| `LkTreePicker` | 目录/知识库选择 | 多选/目录全选级联 |
| `LkSwitchList` | 插件开关列表 | 加载/失败重试/空 |
| `LkDebugDrawer` | 右侧调试抽屉 | 默认 400px |
| `LkChatWindow` | 对话窗 | 流式光标/引导问题/多模态输入 |
| `LkSessionList` | 会话列表 | Tab/搜索/空 |
| `LkQuotaBadge` | 版本徽标+配额面板 | 超限提示/升级入口 |
| `LkVersionGate` | 功能版本门禁 | 低版本置灰+升级引导 |
| `LkJsonViewer` | JSON/变量查看 | 递归折叠（expandDepth） |
| `useSseStream` | SSE 流式 hook | 重连（指数退避）/结束/错误 |
| `LkFileUploader` | 文件上传 | 进度/类型校验/大小超限 |
| `LkCopyField` | 复制字段 | 复制成功反馈（2s） |

每个组件均有组件测试（`src/components/*/*.test.ts`），作为 Storybook 的等价文档：

```bash
pnpm --filter @linkai/ui test
```
