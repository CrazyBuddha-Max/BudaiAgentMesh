# BudaiAgentMesh — 智能体数据中台

> 面向 AI Agent 生态的"数据操作系统"：向下整合企业数据资产，向上赋能智能体高效、安全、协同地工作。

## 定位

不是简单的数据库或数据仓库，而是承上启下的数据操作系统：

- **向下** 整合企业数据资产（数据库、消息、文件、API、SaaS、湖仓）
- **向上** 赋能智能体（语义检索、工具调用、事件订阅、记忆注入、协作编排）

## 五大层次

| 层 | 名称 | 职责 | 状态 |
| --- | --- | --- | --- |
| ① | 数据统一接入层 | 连接器市场 / 采集引擎 / Schema 注册 / 元数据目录 | 已实现 (postgres/mysql/csv) |
| ② | 知识沉淀层 | RAG 流水线 (解析/切分/向量化/语义检索) · 指标语义层 · 知识库 | 已实现 |
| ③ | 多 Agent 协同层 | Agent 注册 / 模板市场 / 工具注册中心 (MCP 雏形) / 真并行 DAG 编排 / 事件总线 | 已实现 |
| ④ | 安全治理层 | IAM (JWT/RBAC) · 动态脱敏 · 审计日志 · 数据血缘 | 已实现 |
| ⑤ | 效果反馈层 | 运行指标 · 任务反馈闭环 · 评分统计 | 已实现 |

## 当前进度 (2025-08)

| 指标 | 数值 |
| --- | --- |
| 后端 API 端点 | 46 个 (接入 12 / 知识 9 / 协同 12 / 安全 6 / 反馈 4 / 系统 2) |
| 数据模型表 | 13 张 |
| 前端页面 | 9 个 |
| 自动化测试 | 21 项, 全部通过 (接入 6 / 知识 6 / 协同 1 / M3 安全反馈 5 / M4 总线模板并行 3) |
| 代码质量 | ruff 全绿 |

### 分层实现明细

**① 数据统一接入层** (app/access)
- 连接器市场: PostgreSQL / MySQL / CSV, 统一 `SourceContract` 契约 (发现/采样/聚合/鉴权参数)
- 采集引擎: Schema 自动发现 + 质量初检 (空值率/区分度/采样值) + 采集任务留痕
- 元数据目录: 数据源 CRUD / 表列检索 / 目录统计 / 数据样例查询

**② 知识沉淀层** (app/knowledge)
- RAG 流水线: 文档解析 (txt/md/html/pdf) → 段落+重叠切分 → 向量化 (HashEmbedder 离线兜底 / OpenAI 可插拔) → 余弦语义检索
- 指标语义层: 指标定义 CRUD + 表达式白名单校验 (expr.py) + 聚合查询/维度下钻/越权拦截
- 检索接口抽象: M3 迁移 pgvector/Milvus 不动业务代码

**③ 多 Agent 协同层** (app/agents)
- Agent 注册中心: 身份 / 能力声明 (Capability Manifest) / 状态管理
- Agent 模板市场 (M4): 预置 5 个角色模板 (分析助手/检索员/分析员/报告员/审计员), 一键创建
- 工具注册中心 (MCP 雏形): `knowledge.retrieve` / `catalog.search_tables` / `data.query_table`, JSON Schema 暴露
- 真并行 DAG 编排 (M4): 知识检索 ∥ 目录检索 各分支独立会话 asyncio.gather, 分工到具能力的 Agent
- 事件总线 (M4): 进程内队列 + Worker 分发 (配置 KAFKA_BROKERS 自动切 Kafka 适配器), 事件直落库 + 总线发布

**④ 安全治理层** (app/security)
- JWT 签发校验 + 内置账号 RBAC 三级角色 (viewer/analyst/admin)
- 动态脱敏 (M3): 敏感列自动识别 (手机/身份证/银行卡/邮箱/姓名/地址) + 按角色掩码 (viewer/analyst 掩码, admin 明文)
- 审计日志 (M3): 全链路操作留痕 (登录/采集/指标查询/数据采样/Agent 任务), 独立会话写入不阻断业务
- 数据血缘 (M3): 源表 → 指标 → 任务 → 结果, 图结构可查询
- 接口级权限门槛 + 指标维度越权拦截 + SQL 标识符白名单防注入 + Fernet 口令加密

**⑤ 效果反馈层** (app/feedback)
- 运行指标: 请求量 / 平均时延 / P95 / 错误率 / 状态码分布 (滑动窗口)
- 反馈闭环 (M3): Agent 任务评分 (1-5 星) + 评论, 与任务/Trace 绑定可回溯, 评分统计驱动迭代

## 技术栈

- **后端**: Python 3.11+/3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL/SQLite · Fernet 口令加密 · JWT · PyMuPDF
- **前端**: React 19 · TypeScript · Vite · @astryxdesign/core · @astryxdesign/theme-neutral · ECharts · TanStack Query
- **部署**: Docker Compose (postgres + backend + frontend)

## 快速开始 (Windows, 推荐一键脚本)

在资源管理器中双击 `BudaiAgentMesh\start_all.bat`,
或打开 cmd 执行:

```bat
cd /d D:\code\budai\Budai-company\BudaiAgentMesh
start_all.bat
```

脚本会自动: 定位 Python -> 创建 Windows venv -> 安装依赖 -> 生成演示数据 -> 启动前后端。
批处理文件为纯 ASCII 编写, 兼容任意 Windows 代码页。

> 需要 Python 3.12 (勾选 Add to PATH) 与 Node.js (npm) 已安装。

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

- [x] **M1**: 数据接入 + 元数据目录 + RBAC 权限 + 基础观测
- [x] **M2**: 知识沉淀 + 多 Agent 协同
  - [x] RAG 流水线: 文档解析 / 切分 / 向量化 / 语义检索
  - [x] 指标语义层: 统一口径 / 绑定目录表 / 聚合查询与维度下钻
  - [x] Agent 注册中心 + 工具注册中心 (MCP 雏形)
  - [x] 任务编排引擎 + 事件全链路留痕
- [x] **M3**: 安全治理增强 + 反馈闭环
  - [x] 动态脱敏: 敏感列识别 + 按角色掩码
  - [x] 审计日志 + 数据血缘 (独立会话, 不阻断业务)
  - [x] 多 Agent 协作编排 (主控 + 检索员 + 分析员分工)
  - [x] 任务反馈闭环: 评分 + 评论 + 统计
- [x] **M4**: 编排并行化 + 事件总线 + Agent 模板市场 (当前)
  - [x] 真并行 DAG: 并行分支独立会话, asyncio.gather
  - [x] 事件总线: 进程内队列 + Worker (KAFKA_BROKERS 可切 Kafka)
  - [x] Agent 模板市场: 5 个预置角色, 一键创建
- [ ] **M5**: 多租户 + 联邦接入 + 连接器/Agent 开放生态

## 测试

```bash
cd backend
../.venv/bin/python -m pytest tests/ -q    # 21 项核心测试
```

## 版本控制

- 远程仓库: `https://github.com/CrazyBuddha-Max/BudaiAgentMesh.git` (分支 `master`)
- 本地提交后推送: `git push -u origin master` (Windows 侧需完成 GitHub 认证)
