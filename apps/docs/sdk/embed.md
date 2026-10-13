# 网页嵌入 SDK

::: warning 骨架阶段
本文档为占位骨架；SDK 本体（iframe Shadow DOM 隔离、样式配置、页面排除、图像/语音开关、转人工）由 apps/embed-sdk 工单交付后补全。
:::

## 快速接入

```html
<script src="https://cdn.link-ai.tech/embed-sdk.min.js"
        data-app-code="YOUR_APP_CODE"></script>
```

## 能力清单

- 对话窗样式配置（位置、主题色、欢迎语）
- 页面排除配置（指定路径不展示对话窗）
- 图像 / 语音输入开关
- 转人工入口
- 样式严格隔离（iframe + Shadow DOM），不影响宿主页面
