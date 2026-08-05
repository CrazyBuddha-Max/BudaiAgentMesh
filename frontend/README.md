# BudaiAgentMesh 前端 (Astryx)

React 19 + TypeScript + Vite + Astryx 设计系统 (`@astryxdesign/core`) + 中性极简主题 (`@astryxdesign/theme-neutral`)。

## 本地开发 (Windows)

```bat
:: 1. 后端 (窗口 1) — 也可直接双击 backend\start_dev.bat
cd backend
start_dev.bat        :: 自动建 venv + 装依赖 + 种子数据 + 启动

:: 2. 前端 (窗口 2)
cd frontend
start_dev.bat        :: npm install + vite dev
```

或双击项目根的 `start_all.bat` 一键同时启动前后端。
访问 `http://localhost:5173`。

## 演示账号

| 账号 | 密码 | 角色 | 权限 |
| --- | --- | --- | --- |
| admin | admin123 | 管理员 | 全部 |
| analyst | analyst123 | 分析师 | 数据源管理 / 采集 / 检索 |
| viewer | viewer123 | 访客 | 只读检索 |

## 页面

- `/dashboard` 数据资产: 接入规模与质量总览
- `/sources` 数据源管理: 连接器市场、接入表单、测试连接、采集、删除
- `/catalog` 元数据目录: 表与字段检索、质量初检画像
- `/security` 安全治理: RBAC 矩阵、账号、治理能力演进
- `/observability` 运行观测: 请求量、时延、错误率、状态码分布

## UI 规范

- 页面禁止使用表情符号
- 遵循 Astryx 中性主题, 信息密度优先、留白克制
- 所有关键操作提供即时反馈 (loading / toast / 乐观更新)

## 构建

```bash
npm run build   # 产物 dist/
```
