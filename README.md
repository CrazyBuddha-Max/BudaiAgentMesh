# BudaiAgentMesh — 智能体数据中台

> 面向 AI Agent 生态的"数据操作系统"：向下整合企业数据资产，向上赋能智能体高效、安全、协同地工作。

## 定位

不是简单的数据库或数据仓库，而是承上启下的数据操作系统：

- **向下** 整合企业数据资产（数据库、消息、文件、API、SaaS、湖仓）
- **向上** 赋能智能体（语义检索、工具调用、事件订阅、记忆注入、协作编排）

## 五大层次

| 层 | 名称 | 职责 | M1 状态 |
| --- | --- | --- | --- |
| ① | 数据统一接入层 | 连接器市场 / 采集引擎 / Schema 注册 / 元数据目录 | 已实现 (postgres/mysql/csv) |
| ② | 知识沉淀层 | RAG 流水线 / 向量库 / 指标语义层 / Agent 记忆 | 指标语义层已实现, RAG/记忆规划中 (M2) |
| ③ | 多 Agent 协同层 | 编排引擎 / 消息总线 / 工具注册中心 (MCP) | 规划中 (M2) |
| ④ | 安全治理层 | IAM (JWT/RBAC) / 脱敏 / 审计 / 血缘 | JWT+RBAC 已实现 |
| ⑤ | 效果反馈层 | 运行指标 / 质量评估 / 反馈闭环 / Trace | 运行指标已实现 |

## 技术栈

- **后端**: Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL/SQLite · Fernet 口令加密 · JWT
- **前端**: React 19 · TypeScript · Vite · @astryxdesign/core · @astryxdesign/theme-neutral
- **部署**: Docker Compose

## 快速开始 (Windows, 推荐一键脚本)

在资源管理器中双击 `BudaiAgentMesh\start_all.bat`,
或打开 cmd 执行:

```bat
cd /d D:\code\budai\Budai-company\BudaiAgentMesh
start_all.bat
```

脚本会自动: 定位 Python -> 创建 Windows venv -> 安装依赖 -> 生成演示数据 -> 启动前后端。

> 注意: 若此前在 WSL 中创建过 `.venv` (Linux 版), Windows 脚本会自动重建为 Windows 版。
> 需要 Node.js (npm) 已安装并加入 PATH。

## 快速开始 (手动分步)

```bat
:: 后端 (窗口 1)
cd /d D:\code\budai\Budai-Company\BudaiAgentMesh\backend
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m scripts.seed_demo
.venv\Scripts\python -m uvicorn app.main:app --port 8000

:: 前端 (窗口 2)
cd /d D:\code\budai\Budai-Company\BudaiAgentMesh\frontend
npm install
npm run dev
```

> 关键区别: Windows 下 venv 路径是 `.venv\Scripts\python.exe`, 不是 `.venv/bin/python`。

演示账号: `admin/admin123` (管理员) · `analyst/analyst123` (分析师) · `viewer/viewer123` (访客)

## Docker 一键部署

```bash
cd deploy
docker compose up -d --build
# 前端 http://localhost:8080  后端 http://localhost:8000/docs
```

## 文档

- [系统整体架构设计](docs/ARCHITECTURE.md)
- [后端接口] 启动后访问 http://localhost:8000/docs (OpenAPI)
- [前端说明](frontend/README.md)

## 里程碑

- [x] M1: 数据接入 + 元数据目录 + RBAC 权限 + 基础观测
- [ ] M2: 知识沉淀 (RAG/向量/指标语义) + 多 Agent 协同 (编排/MCP)
  - [x] 指标语义层: 统一口径 / 绑定目录表 / 可执行聚合查询 (CRUD API + 指标语义页)
  - [ ] RAG 流水线 / 向量库 / Agent 记忆
  - [ ] 编排引擎 / 消息总线 / MCP 工具注册
- [ ] M3: 细粒度权限 + 动态脱敏 + 审计血缘 + 反馈闭环
- [ ] M4: 连接器/Agent 开放生态 + 多租户 + 联邦接入

## 测试

```bash
cd backend
../.venv/bin/python -m pytest tests/ -q    # 6 项核心测试
```
