# Frontend Docs 总览

## 目标

汇总前端体验、页面数据来源和 Web API 消费边界。前端文档只定义展示形态和交互需求，不定义后端字段的唯一来源。

## 文档归属

| 文档 | 职责 |
| :--- | :--- |
| [frontend_design.md](frontend_design.md) | 前端页面、布局、视觉规范、页面级数据需求 |
| [../web_api/README.md](../web_api/README.md) | 前端可消费协议入口、事件类型、REST/WS 边界 |
| [../Arch/arch.md](../Arch/arch.md) | Layer 4 架构边界和前端不得跨越的系统边界 |
| [../internal_contracts/channel_routing.md](../internal_contracts/channel_routing.md) | 内部频道到 Web API 事件的转换来源 |

## 对齐规则

- 页面需要什么信息，先写在 `frontend_design.md`。
- 字段、枚举、错误码、恢复流程以 `../web_api` 为准。
- 内部来源、可见性和禁止透传规则以 `../internal_contracts` 为准。
- 架构层只记录边界和长期取舍，不承载页面细节。

## 当前状态

当前仓库尚未包含 `frontend/` 代码目录，前端设计文档暂归档在 `docs/frontend`。创建前端工程后，可在 `frontend/docs` 建立实现侧文档，但不得复制一份脱离 `docs/web_api` 的协议定义。
