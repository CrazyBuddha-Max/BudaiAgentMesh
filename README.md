# BudaiAgentMesh — 智能体数据中台

> 面向 AI Agent 生态的"数据操作系统"：向下整合企业数据资产，向上赋能智能体高效、安全、协同地工作。

## 定位

不是简单的数据库或数据仓库，而是承上启下的数据操作系统：

- **向下** 整合企业数据资产（数据库、消息、文件、API、SaaS、湖仓）
- **向上** 赋能智能体（语义检索、工具调用、事件订阅、记忆注入、协作编排）

## 五大层次


| 层   | 名称          | 职责                                                    | 状态                       |
| --- | ----------- | ----------------------------------------------------- | ------------------------ |
| ①   | 数据统一接入层     | 连接器市场 / 采集引擎 / Schema 注册 / 元数据目录                      | 已实现 (postgres/mysql/csv) |
| ②   | 知识沉淀层       | RAG 流水线 (解析/切分/向量化/语义检索) · 指标语义层 · 知识库                | 已实现                      |
| ③   | 多 Agent 协同层 | Agent 注册 / 模板市场 / 工具注册中心 (MCP 雏形) / 真并行 DAG 编排 / 事件总线 | 已实现                      |
| ④   | 安全治理层       | IAM (JWT/RBAC) · 动态脱敏 · 列级权限 · 审计日志 · 数据血缘 · 生命周期     | 已实现                      |
| ⑤   | 效果反馈层       | 运行指标 · 任务反馈闭环 · 评分统计                                  | 已实现                      |
| ⚡   | MCP Server  | 完整 Model Context Protocol 端点 (/mcp/mcp), 4 个数据工具      | 已实现 (M5)                 |


## 当前进度 (2025-08)


| 指标         | 数值                                  |
| ---------- | ----------------------------------- |
| 后端 API 端点  | 50+ 个                               |
| 数据模型表      | 14 张 (含列权限规则)                       |
| 前端页面       | 9 个                                 |
| 自动化测试      | 37 项, 全部通过 (M6 新增向量后端/增量采集/SSO 13 项)  |
| MCP Server | /mcp/mcp (streamable-http), 4 个数据工具 |
| 代码质量       | ruff 全绿                             |


### 分层实现明细

**① 数据统一接入层** (app/access)

- 连接器市场: PostgreSQL / MySQL / CSV, 统一 `SourceContract` 契约 (发现/采样/聚合/鉴权参数)
- 采集引擎: Schema 自动发现 + 质量初检 (空值率/区分度/采样值) + 采集任务留痕
- 元数据目录: 数据源 CRUD / 表列检索 / 目录统计 / 数据样例查询

**② 知识沉淀层** (app/knowledge)

- RAG 流水线: 文档解析 (txt/md/html/pdf) → 段落+重叠切分 → 向量化 (HashEmbedder 离线兜底 / OpenAI 可插拔) → 语义检索
- 可插拔向量后端 (M6): 默认全量余弦 / PostgreSQL pgvector (`<=>` 距离 SQL 端排序) / Milvus, 接口保持业务无感
- 指标语义层: 指标定义 CRUD + 表达式白名单校验 (expr.py) + 聚合查询/维度下钻/越权拦截

**③ 多 Agent 协同层** (app/agents)

- Agent 注册中心: 身份 / 能力声明 (Capability Manifest) / 状态管理
- Agent 模板市场 (M4): 预置 5 个角色模板 (分析助手/检索员/分析员/报告员/审计员), 一键创建
- 工具注册中心 (MCP 雏形): `knowledge.retrieve` / `catalog.search_tables` / `data.query_table`, JSON Schema 暴露
- 真并行 DAG 编排 (M4): 知识检索 ∥ 目录检索 各分支独立会话 asyncio.gather, 分工到具能力的 Agent
- 事件总线 (M4): 进程内队列 + Worker 分发 (配置 KAFKA_BROKERS 自动切 Kafka 适配器), 事件直落库 + 总线发布

**④ 安全治理层** (app/security)

- JWT 签发校验 + 内置账号 RBAC 三级角色 (viewer/analyst/admin)
- 动态脱敏 (M3): 敏感列自动识别 (手机/身份证/银行卡/邮箱/姓名/地址) + 按角色掩码
- 细粒度列级权限 (M5): 按角色禁止访问指定列, 与脱敏叠加 (数据采样/指标维度双拦截)
- 审计日志 (M3): 全链路操作留痕, 独立会话写入不阻断业务
- 数据血缘 (M3): 源表 → 指标 → 任务 → 结果, 图结构可查询
- 数据生命周期 (M5): 保留期策略 + 状态评估 (活跃/临期/过期), 到期时间自动计算
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

脚本会自动: 定位 Python -&gt; 创建 Windows venv -&gt; 安装依赖 -&gt; 生成演示数据 -&gt; 启动前后端。
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
- [15 分钟上手教程](docs/USER_GUIDE.md)
- [后端接口] 启动后访问 [http://localhost:8000/docs](http://localhost:8000/docs) (OpenAPI)
- [前端说明](frontend/README.md)

## 里程碑

- [x] **M1**: 数据接入 + 元数据目录 + RBAC 权限 + 基础观测
- [x] **M2**: 知识沉淀 + 多 Agent 协同
  - [x] RAG 流水线 / 指标语义层 / Agent 注册 + 工具注册中心 / 任务编排
- [x] **M3**: 安全治理增强 + 反馈闭环
  - [x] 动态脱敏 / 审计日志 / 数据血缘 / 任务反馈闭环
- [x] **M4**: 编排并行化 + 事件总线 + Agent 模板市场
  - [x] 真并行 DAG / 事件总线 (Kafka 适配) / Agent 模板市场
- [x] **M5**: MCP Server + 细粒度权限 + 生命周期 (当前)
  - [x] 完整 MCP Server (/mcp/mcp, 4 工具, 任意 MCP 客户端可调用)
  - [x] 列级权限: 按角色禁止列访问, 数据/指标双拦截
  - [x] 数据生命周期: 保留期策略 + 状态评估
- [ ] **M6**: 多租户 + 联邦接入 + CDC 增量 (数据库级) + 多租户隔离
  - [x] 可插拔向量后端 (M6-1): pgvector (`<=>` 余弦距离) / Milvus 适配, 接口保持业务无感
  - [x] SSO / OAuth2.0 登录 (M6-2): 通用 OIDC 授权码流 + 内置演示 IdP + 前端一键登录
  - [x] OTel 观测 (M6-3): OTLP/HTTP span 上报 (采集/入库/Agent 任务), 零额外依赖, 未配置零开销
  - [x] CDC 增量采集 (M6-4): 文件指纹水位线, 无变化跳过重采 (PostgreSQL/MySQL 级 CDC 待 M6+)

## 测试

```bash
cd backend
../.venv/bin/python -m pytest tests/ -q    # 37 项核心测试
```

