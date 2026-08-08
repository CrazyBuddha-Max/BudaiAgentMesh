# BudaiAgentMesh 智能体数据中台 — 系统整体架构设计

> 版本: v0.2 (已落地实现)
> 状态: M1–M6 已完成 (2026-08), 本文标注 ✓ 为已实现项, 其余为演进展望
> 定位: 面向 AI Agent 生态的"数据操作系统"，向下整合企业数据资产，向上赋能智能体高效、安全、协同地工作。

---

## 1. 项目定位与设计原则

### 1.1 它是什么

BudaiAgentMesh 不是简单的数据库或数据仓库，而是专门为 AI Agent 生态设计的数据操作系统。
它解决的核心矛盾是：**智能体需要"机器可理解、权限可控、质量可信、可迭代进化"的数据供给**，
而传统数仓只提供"人可查询的静态数据"。

### 1.2 与传统数仓的差异

| 维度 | 传统数仓 | BudaiAgentMesh |
| --- | --- | --- |
| 消费对象 | 人 (BI/报表) | 人与 Agent 并存，Agent 为主 |
| 数据形态 | 结构化表 | 结构化 + 非结构化 + 向量 + 图谱 + 指标语义 |
| 供给方式 | SQL 查询 | 语义检索 + 工具调用 + 事件订阅 + 记忆注入 |
| 安全模型 | 表级权限 | 行/列/单元格级 + 动态脱敏 + 上下文感知授权 |
| 反馈机制 | 无 | 闭环反馈驱动知识与检索持续进化 |
| 协作能力 | 无 | 多 Agent 共享数据上下文、消息总线、编排调度 |

### 1.3 设计原则

1. **语义优先 (Semantic-First)** — 数据以业务语义 (指标口径、实体关系) 组织，而非物理表组织。
2. **安全内建 (Security by Design)** — 权限、脱敏、审计贯穿全链路，而非事后附加。
3. **契约化接入 (Contract-Based)** — 所有数据源与工具通过统一契约接入，Agent 只面向契约编程。
4. **反馈闭环 (Feedback Loop)** — 每一次 Agent 执行结果都回流，驱动知识、质量、检索持续进化。
5. **极简交互 (Minimal UX)** — 前端采用 Astryx 极简主题，无表情符号，以信息密度与操作效率为美。

---

## 2. 总体架构

```
+------------------------------------------------------------------------------------+
|                          BudaiAgentMesh 智能体数据中台                               |
+------------------------------------------------------------------------------------+
|                                                                                    |
|  +------------------------------  表现层 (Astryx 前端)  ---------------------------+|
|  |  数据资产门户 | 知识工作台 | Agent 协同控制台 | 安全治理台 | 效果观测台           ||
|  +------------------------------------------------------------------------------- +|
|                                    |  REST / WebSocket / SSE                        |
|  +------------------------------  应用层 (Python 服务)  ---------------------------+|
|  |  API Gateway (FastAPI) · 统一鉴权 · 限流 · 请求路由                             ||
|  +-------------------------------------------------------------------------------+|
|                                                                                    |
|  +--------------------------------------------------------------------------------+|
|  | ⑤ 效果反馈层  Feedback Loop                                                     ||
|  |  指标监控 · 质量评估 · 反馈采集 · Trace 追踪 · 数据血缘 · 迭代闭环                 ||
|  +--------------------------------------------------------------------------------+|
|  +--------------------------------------------------------------------------------+|
|  | ④ 安全治理层  Security & Governance                                             ||
|  |  IAM/JWT/RBAC/SSO · 多租户隔离 · 列级权限 · 动态脱敏 · 审计 · 生命周期 · 血缘  ||
|  +--------------------------------------------------------------------------------+|
|  +--------------------------------------------------------------------------------+|
|  | ③ 多 Agent 协同层  Agent Collaboration                                          ||
|  |  Agent 注册/生命周期 · 编排引擎 · 任务调度 · 消息总线 · 工具注册中心 (MCP)        ||
|  +--------------------------------------------------------------------------------+|
|  +--------------------------------------------------------------------------------+|
|  | ② 知识沉淀层  Knowledge Layer                                                   ||
|  |  RAG 流水线 · 向量库 · 知识图谱 · 指标语义层 · Agent 记忆 (长期/短期/经验)        ||
|  +--------------------------------------------------------------------------------+|
|  +--------------------------------------------------------------------------------+|
|  | ① 数据统一接入层  Data Access Layer                                             ||
|  |  连接器市场 · CDC/批量/实时 · Schema 注册 · 数据质量初检 · 元数据目录             ||
|  +--------------------------------------------------------------------------------+|
|                                                                                    |
|  +------------------------------  基础设施层  ------------------------------------+|
|  |  PostgreSQL · Milvus · Neo4j · Kafka · MinIO · Redis · 对象存储                 ||
|  +--------------------------------------------------------------------------------+|
+------------------------------------------------------------------------------------+
```

### 分层职责一句话概括

| 层 | 一句话职责 | 关键交互对象 |
| --- | --- | --- |
| ① 数据统一接入层 | 把企业任意数据源变成"统一、干净、可发现"的数据资产 | 企业数据库/消息/文件/API/SaaS |
| ② 知识沉淀层 | 把数据资产加工成"机器可直接消费的知识" | 向量库、图谱、指标语义、Agent 记忆 |
| ③ 多 Agent 协同层 | 让多个 Agent 安全、有序、共享地调用数据与工具完成复杂任务 | 外部智能体、内部子 Agent、MCP 工具 |
| ④ 安全治理层 | 让每一次数据供给都"可授权、可脱敏、可审计、可溯源" | 全链路横切 |
| ⑤ 效果反馈层 | 让每一次执行都留下数据，驱动系统持续进化 | 全链路横切 |

---

## 3. 分层详细设计

### 3.1 数据统一接入层 (Data Access Layer)

**目标**: 向下整合企业数据资产 —— "接入即治理，接入即目录"。

**核心模块 (已实现 ✓ / 展望):**

1. **连接器市场 (Connector Marketplace)**
   - ✓ PostgreSQL / MySQL / CSV (统一 `SourceContract`: 发现/采样/聚合/增量检测)
   - 展望: Oracle / SQL Server / MongoDB / Kafka / S3 / SaaS 连接器

2. **采集引擎 (Ingestion Engine)**
   - ✓ 批量采集 + 增量 watermark 指纹 (CSV 文件指纹; PG/MySQL 表指纹: 行数+列集合)
   - ✓ 采集任务留痕 (ingestion_runs)
   - 展望: Debezium 级 CDC、断点续传、批流一体

3. **Schema 注册中心 (Schema Registry)**
   - ✓ 自动 schema 推断 (information_schema 扫描) + 字段质量画像
   - 展望: 版本化、兼容性校验、口径绑定

4. **数据质量初检 (Pre-Quality)**
   - ✓ 空值率 / 区分度 / 采样值 → 表级质量分

5. **元数据目录 (Metadata Catalog)**
   - ✓ 数据源 CRUD / 表列检索 / 目录统计 / 数据样例查询
   - ✓ **多租户隔离 (M6)**: 目录按 tenant 硬隔离
   - ✓ **联邦接入 (M6)**: 远端实例目录/数据 Bearer 透传, 并发检索

**技术选型**: Python `asyncio` + 连接器插件化 (装饰器注册), 目录存 PostgreSQL/SQLite, 增量用 watermark 指纹 (M6).

---

### 3.2 知识沉淀层 (Knowledge Layer)

**目标**: 把"数据"沉淀为"知识" —— 让 Agent 检索到的不只是记录，而是口径正确的业务知识。

**核心模块 (已实现 ✓ / 展望):**

1. **RAG 流水线 (Document Intelligence)**
   - ✓ 解析: PDF / Markdown / HTML / TXT → 结构化 chunk (PyMuPDF)
   - ✓ 切分: 段落优先 + 重叠窗口
   - ✓ 向量化: HashEmbedder (离线兜底) / OpenAI (可插拔)
   - ✓ 检索: 可插拔向量后端 (全量余弦 / pgvector `<=>` / Milvus), 接口无感

2. **知识图谱 (Knowledge Graph)**
   - ✓ 轻量数据血缘 (源表 → 指标 → 任务 → 结果)
   - 展望: 实体抽取与关系图谱 (Neo4j)

3. **指标语义层 (Semantic Metrics Layer)**
   - ✓ 指标定义 CRUD + 表达式白名单校验 + 聚合查询/维度下钻/越权拦截

4. **Agent 记忆 (Agent Memory)**
   - 展望: 长期/短期/经验记忆

5. **知识质量管理**
   - 展望: 覆盖率 / 新鲜度 / RAGAS 评估

**技术选型**: 向量库 pgvector/Milvus (M6 可插拔), Embedding 可插拔 (OpenAI/本地哈希), 解析 PyMuPDF.

---

### 3.3 多 Agent 协同层 (Agent Collaboration Layer)

**目标**: 向上赋能智能体 —— 让外部 Agent 与内部子 Agent 安全、有序、共享地工作。

**核心模块 (已实现 ✓ / 展望):**

1. **Agent 注册中心 (Agent Registry)**
   - ✓ Agent 身份 / 能力声明 (Capability Manifest) / 状态管理
   - ✓ Agent 模板市场 (M4): 5 个预置角色模板一键创建

2. **编排引擎 (Orchestration Engine)**
   - ✓ Pipeline 编排 + 真并行 DAG (asyncio.gather, 各分支独立会话)
   - 展望: 超时/重试/降级策略、Swarm/Debate 模式

3. **消息总线 (Message Bus)**
   - ✓ 进程内队列 + Worker 分发; 配置 `KAFKA_BROKERS` 自动切 Kafka 适配器
   - ✓ 事件直落库 + 总线发布

4. **工具注册中心 (Tool Registry, MCP)**
   - ✓ 数据能力以标准工具暴露 (JSON Schema): 知识检索 / 目录检索 / 数据查询 / 指标查询
   - ✓ 完整 MCP Server (M5): `/mcp/mcp` (streamable-http), 任意 MCP 客户端可调用

5. **统一 Agent API**
   - ✓ REST 任务接口 (创建/执行/事件链路/反馈)
   - 展望: SSE/WebSocket 网关、Trace ID 全链路

---

### 3.4 安全治理层 (Security & Governance)

**目标**: 每一次数据供给都"可授权、可脱敏、可审计、可溯源"。

**核心模块 (已实现 ✓ / 展望):**

1. **身份与访问 (IAM)**
   - ✓ JWT 签发/校验 + 内置账号 RBAC 三级角色 (viewer/analyst/admin)
   - ✓ **SSO / OAuth2.0 (M6)**: 通用 OIDC 授权码流 + 内置演示 IdP (`/mock-idp`)
   - ✓ **多租户 (M6)**: JWT 携带 tenant 声明, 数据接入层硬隔离 (越权视为不存在)
   - 展望: ABAC 策略引擎 (OPA)、Keycloak 接入

2. **精细化数据权限 (Fine-Grained ACL)**
   - ✓ 列级权限 (M5): 按角色禁止访问列, 数据采样/指标维度双拦截
   - 展望: 行级/单元格级、血缘传导继承

3. **隐私与脱敏 (Privacy & Masking)**
   - ✓ 敏感列自动识别 (手机/身份证/银行卡/邮箱/姓名/地址) + 按角色动态掩码
   - 展望: 泛化/扰动/令牌化、静态加密分列

4. **审计与追溯 (Audit & Lineage)**
   - ✓ 全链路审计日志 (登录/采集/指标/采样/Agent 任务), 独立会话写入
   - ✓ 数据血缘: 源表 → 指标 → 任务 → 结果 图结构

5. **合规治理 (Compliance)**
   - ✓ 数据生命周期 (M5): 保留期策略 + 状态评估 (活跃/临期/过期)
   - ✓ 口令 Fernet 加密存储

**技术选型**: 自研 JWT/RBAC + 内置 OIDC 客户端 (M6) + Fernet 加密, 审计/血缘存 PostgreSQL/SQLite.

---

### 3.5 效果反馈层 (Feedback Loop)

**目标**: 让每一次执行都留下数据，驱动系统持续进化 —— "用得好，系统才会越来越好用"。

**核心模块 (已实现 ✓ / 展望):**

1. **运行指标监控 (Runtime Metrics)**
   - ✓ 请求量 / 平均时延 / P95 / 错误率 / 状态码分布 (滑动窗口)
   - 展望: 任务成功率/Token 成本、告警

2. **质量评估 (Quality Evaluation)**
   - ✓ 数据质量评分 (空值率/区分度)
   - 展望: MRR / NDCG / RAGAS

3. **反馈采集 (Feedback Capture)**
   - ✓ Agent 任务 1-5 星评分 + 评论, 与任务绑定可回溯
   - ✓ 评分统计 (by_rating / avg) 驱动迭代

4. **Trace 与血缘可视化 (Observability)**
   - ✓ **OTel (M6)**: OTLP/HTTP span 上报 (采集/入库), 零额外依赖, 未配置零开销
   - ✓ 数据血缘图查询
   - 展望: LLM 全链路 Trace (请求→检索→生成)

5. **迭代闭环 (Iteration Loop)**
   - ✓ 反馈 → 统计 → 展示 (驱动人工迭代)
   - 展望: 自动知识修正 / 检索重排

**技术选型**: 进程内指标 (M1) + OTLP/HTTP 遥测 (M6) + 反馈存 PostgreSQL/SQLite.

---

## 4. 端到端调用链示例

```
用户/外部Agent 提问: "本季度华东区各产品线的毛利率是多少？"

① 接入层:     元数据目录命中"毛利率"指标，定位到 fact_sales + dim_region + dim_product
② 知识层:     指标语义层解析口径 (毛利率 = (收入-成本)/收入，华东 = region='east')
              向量库检索到相关产品定义与历史分析文档
③ 协同层:     编排引擎分解任务: [查指标] → [读文档] → [生成结论]，调度子Agent并行执行
④ 安全层:     鉴权 → ABAC 判断该 Agent 无华东以外区域权限 → 行级裁剪 → 动态脱敏
⑤ 反馈层:     生成结果 + 全链路 Trace 落库，等待显式/隐式反馈回流
```

---

## 5. 技术栈清单

### 后端 (Python)

| 类别 | 选型 |
| --- | --- |
| 语言/运行时 | Python 3.12 + asyncio |
| API 框架 | FastAPI + Pydantic v2 |
| 数据访问 | SQLAlchemy 2.0 + Alembic |
| 异步任务 | Celery + Redis (或 Arq) |
| 调度 | APScheduler / Celery Beat |
| 消息 | Kafka (事件流) + Redis Streams (轻量协作) |
| 向量库 | Milvus (生产) / pgvector (起步) |
| 图数据库 | Neo4j |
| 业务元数据 | PostgreSQL 16 |
| 对象存储 | MinIO / S3 |
| CDC | Debezium |
| 策略引擎 | OPA |
| RAG | LlamaIndex 或自研流水线 + unstructured |
| Agent 协议 | MCP Python SDK |
| 可观测性 | OpenTelemetry + Prometheus |
| 测试 | pytest + ruff + mypy |

### 前端 (Astryx)

| 类别 | 选型 |
| --- | --- |
| 框架 | React 19 + TypeScript |
| 构建 | Vite 6 |
| 组件库 | @astryxdesign/core (可访问性、主题化、深色模式) |
| 主题 | @astryxdesign/theme-neutral (极简、克制) |
| 脚手架 | @astryxdesign/cli |
| 样式 | @stylexjs/stylex (Astryx 内置) |
| 状态管理 | Zustand |
| 数据请求 | TanStack Query + Axios (SSE 用 EventSource) |
| 图表 | ECharts (数据资产/监控大屏) + visx (轻量交互图) |
| 路由 | React Router v7 |

> UI 规范: 页面禁用表情符号；遵循"信息密度优先、留白克制"的极简风格；所有关键操作有即时反馈 (loading/乐观更新/错误提示)。

---

## 6. 代码目录规划 (已对齐实际)

```
BudaiAgentMesh/
├── README.md                     # 项目总览与进度
├── docs/
│   ├── ARCHITECTURE.md           # 本文档
│   └── USER_GUIDE.md             # 15 分钟上手教程
├── backend/                      # Python 后端 (分层包)
│   ├── app/
│   │   ├── api/                  # FastAPI 路由 (access/agents/knowledge/security/feedback/health)
│   │   ├── access/               # ① 数据统一接入层
│   │   │   ├── connectors/       #    连接器市场 (csv/mysql/postgres/expr)
│   │   │   ├── ingestion.py      #    采集引擎 (含 M6 增量指纹检测)
│   │   │   ├── catalog.py        #    元数据目录 (含 M6 多租户隔离)
│   │   │   ├── federated.py      #    联邦接入 (M6)
│   │   │   └── crypto.py         #    Fernet 口令加密
│   │   ├── knowledge/            # ② 知识沉淀层
│   │   │   ├── service.py        #    RAG 流水线编排 (含 M6 OTel 埋点)
│   │   │   ├── vectorstore.py    #    可插拔向量后端 (M6: 余弦/pgvector/Milvus)
│   │   │   ├── embeddings.py     #    可插拔 Embedding (Hash/OpenAI)
│   │   │   ├── parsers.py        #    文档解析 (txt/md/html/pdf)
│   │   │   ├── chunking.py       #    切分
│   │   │   └── metrics_*.py      #    指标语义层
│   │   ├── agents/               # ③ 多 Agent 协同层
│   │   │   ├── orchestration.py  #    真并行 DAG 编排
│   │   │   ├── mcp_server.py     #    完整 MCP Server (M5)
│   │   │   ├── tools.py          #    工具注册中心
│   │   │   ├── bus.py            #    事件总线 (Kafka 适配)
│   │   │   └── templates.py      #    Agent 模板市场
│   │   ├── security/             # ④ 安全治理层
│   │   │   ├── auth.py           #    JWT/RBAC (M6: tenant 声明)
│   │   │   ├── sso.py            #    SSO/OAuth2.0 OIDC 客户端 (M6)
│   │   │   ├── mock_idp.py       #    内置演示 IdP (M6)
│   │   │   ├── tenant.py         #    多租户实体 (M6)
│   │   │   ├── masking.py        #    动态脱敏
│   │   │   ├── acl.py            #    列级权限
│   │   │   ├── audit.py          #    审计日志
│   │   │   ├── lineage.py        #    数据血缘
│   │   │   └── retention.py      #    生命周期
│   │   ├── feedback/             # ⑤ 效果反馈层
│   │   │   ├── metrics.py        #    运行指标中间件
│   │   │   └── feedback.py       #    任务反馈闭环
│   │   ├── core/                 # 基础设施
│   │   │   ├── config.py         #    全局配置 (env/.env)
│   │   │   ├── database.py       #    异步引擎 + 轻量迁移
│   │   │   ├── telemetry.py      #    OTLP span (M6)
│   │   │   ├── logging.py / exceptions.py
│   │   └── main.py               # 应用入口 (挂载 MCP + 演示 IdP)
│   ├── tests/                    # 44 项测试 (test_access/agents/knowledge/m3/m4/m5/m6/m6_tenancy)
│   └── scripts/seed_demo.py      # 演示数据
├── frontend/                     # Astryx 前端 (9 个页面)
│   └── src/
│       ├── pages/                # Dashboard/Sources/Catalog/Knowledge/Metrics/Agents/Security/Observability/Login
│       ├── api/                  # REST 客户端 + 类型定义
│       ├── components/ / store/ / theme.tsx
└── deploy/
    └── docker-compose.yml        # 本地一键起 (postgres + backend + frontend)
```

---

## 7. 演进路线 (Roadmap)

| 阶段 | 里程碑 | 范围 | 状态 |
| --- | --- | --- | --- |
| M1 (MVP) | 数据接入 + 目录 + 权限 + 基础观测 | 连接器 (PG/MySQL/CSV)、元数据目录、RBAC、REST API | ✅ 已完成 |
| M2 | 知识沉淀 + Agent 协同 | RAG 流水线、指标语义层、Agent 注册、工具注册中心、任务编排 | ✅ 已完成 |
| M3 | 治理增强 + 反馈闭环 | 动态脱敏、审计日志、数据血缘、任务反馈 | ✅ 已完成 |
| M4 | 编排并行化 + 事件总线 + 模板市场 | 真并行 DAG、EventBus (Kafka 适配)、Agent 模板 | ✅ 已完成 |
| M5 | 开放生态 + 精细治理 | 完整 MCP Server、列级权限、生命周期 | ✅ 已完成 |
| M6 | 规模化 + 可观测 (当前) | 多租户、联邦接入、CDC 增量、SSO/OAuth2.0、pgvector/Milvus、OTel | ✅ 已完成 (2026-08) |
| M7 | 深度规模化 | 租户覆盖知识/Agent 层、逻辑复制 CDC、Prometheus 指标、联邦双向认证 | 🚧 规划中 |

---

## 8. 关键设计决策记录 (ADR 摘要)

1. **五层分治，横切两翼**: 安全治理层与效果反馈层作为横切能力贯穿前三层，避免"事后补安全、事后补观测"。
2. **契约先行**: 所有数据源 (SourceContract) 与工具 (MCP) 先定义契约再实现，Agent 只面向契约编程。
3. **权限血缘传导**: 权限随数据血缘自动继承，避免下游知识库成为权限逃逸口。
4. **反馈绑定可追溯单元**: 每条反馈必须绑定 Trace ID，保证"点赞/点踩"可回溯到具体数据与上下文。
5. **极简 UI 规范**: 禁用表情符号；所有页面遵循 Astryx 中性主题，交互以即时反馈驱动。
