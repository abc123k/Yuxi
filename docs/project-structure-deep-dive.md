# Yuxi 项目结构与深度解析

> Yuxi (v0.6.0) 是一个基于大模型的智能知识库与知识图谱智能体开发平台，融合了 RAG 技术与知识图谱技术，基于 **LangGraph v1 + Vue.js + FastAPI + LightRAG** 架构构建。项目完全通过 Docker Compose 进行管理，支持热重载开发。

---

## 一、整体架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器 (Vue 3 SPA)                    │
│                     web:5173 (Vite Dev Server)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / SSE
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI 后端 (api:5050)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────┐ │
│  │ Routers  │→ │ Services │→ │Reposit.  │→ │  PostgreSQL     │ │
│  │ (HTTP层) │  │ (业务逻辑)│  │ (数据访问)│  │  (业务+知识元数据)│ │
│  └──────────┘  └────┬─────┘  └──────────┘  └─────────────────┘ │
│                     │                                          │
│              ┌──────▼──────┐                                   │
│              │ LangGraph   │  Agent 系统 (Chatbot / DeepAgent)  │
│              │ Agents      │  中间件链 → 工具调用 → 子Agent      │
│              └──────┬──────┘                                   │
│                     │                                          │
│              ┌──────▼──────────────────────────────────────┐   │
│              │          Knowledge Base Engine               │   │
│              │  LightRAG (Milvus向量 + Neo4j图谱)            │   │
│              │  / Milvus-only / Dify Adapter                │   │
│              └──────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ ARQ Worker   │  │ Sandbox      │  │ 文档解析 (MinerU/   │  │
│  │ (异步任务队列)│  │ (沙箱执行)    │  │  PaddleX/DeepSeek)  │  │
│  └──────────────┘  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌────────┐   ┌──────────┐   ┌──────────┐
         │ Neo4j  │   │  Milvus  │   │   MinIO  │
         │ :7687  │   │ :19530   │   │  :9000   │
         │(知识图谱)│   │(向量数据库)│   │(对象存储) │
         └────────┘   └──────────┘   └──────────┘
```

---

## 二、技术栈总览

### 后端技术栈

| 类别 | 技术 | 版本/说明 |
|------|------|-----------|
| Web 框架 | FastAPI | 异步 ASGI 框架 |
| ASGI 服务器 | Uvicorn | 支持热重载 |
| 异步任务队列 | ARQ + Redis | 长耗时 Agent 任务异步执行 |
| Agent 框架 | LangGraph v1 + LangChain | 状态图 + 中间件模式 |
| 知识图谱 | Neo4j + LightRAG | 图数据库 + 图增强检索 |
| 向量数据库 | Milvus v2.5.6 | 高维向量检索 |
| 关系数据库 | PostgreSQL 16 | 业务数据 + 知识元数据 |
| 对象存储 | MinIO | S3 兼容，存储文件/附件 |
| 缓存/消息 | Redis 7 | 任务队列 + 事件流 + 缓存 |
| 文档解析 | MinerU / PaddleX / DeepSeek OCR | 多引擎文档解析 |
| 包管理 | uv | 快速 Python 包管理 |
| 测试 | pytest + pytest-asyncio | 单元/集成/E2E 三层 |

### 前端技术栈

| 类别 | 技术 | 版本/说明 |
|------|------|-----------|
| 框架 | Vue 3 | Composition API |
| 构建工具 | Vite 7 | 快速开发服务器 |
| 状态管理 | Pinia 3 + pinia-plugin-persistedstate | 持久化状态 |
| UI 组件库 | Ant Design Vue 4 | 企业级组件 |
| 路由 | Vue Router 4 | SPA 路由 |
| 图可视化 | Sigma.js + Graphology | 知识图谱渲染 |
| 图表 | ECharts | 数据可视化 |
| 思维导图 | Markmap | Markdown 转思维导图 |
| 图标 | Lucide Vue Next | 现代图标库 |
| 包管理 | pnpm 10 | 高效包管理 |

---

## 三、目录结构

```
Yuxi/
├── backend/                          # Python 后端
│   ├── server/                       #   Web 应用层 (FastAPI)
│   │   ├── main.py                   #     ★ 入口文件
│   │   ├── worker_main.py            #     ARQ Worker 入口
│   │   ├── routers/                  #     HTTP 路由 (16+ 路由模块)
│   │   │   ├── __init__.py           #       路由聚合器
│   │   │   ├── chat_router.py        #       ★ 对话路由 (985行)
│   │   │   ├── knowledge_router.py   #       知识库路由
│   │   │   ├── graph_router.py       #       知识图谱路由
│   │   │   ├── evaluation_router.py  #       评估路由
│   │   │   ├── mindmap_router.py     #       思维导图路由
│   │   │   ├── mcp_router.py         #       MCP 服务器路由
│   │   │   ├── skill_router.py       #       Skills 路由
│   │   │   ├── subagent_router.py    #       子Agent路由
│   │   │   ├── auth_router.py        #       认证路由
│   │   │   ├── system_router.py      #       系统路由
│   │   │   ├── dashboard_router.py   #       仪表盘路由
│   │   │   ├── task_router.py        #       任务路由
│   │   │   ├── tool_router.py        #       工具路由
│   │   │   ├── department_router.py  #       部门路由
│   │   │   ├── apikey_router.py      #       API Key 路由
│   │   │   └── filesystem_router.py  #       文件系统路由
│   │   └── utils/                    #     工具模块
│   │       ├── lifespan.py           #       ★ 应用生命周期
│   │       ├── auth_middleware.py    #       认证中间件
│   │       ├── access_log_middleware.py
│   │       └── common_utils.py
│   │
│   ├── package/yuxi/                 #   核心业务库 (可复用)
│   │   ├── __init__.py               #     配置加载 + 全局 Config 单例
│   │   ├── config/                   #     配置系统
│   │   │   ├── app.py                #       中央配置 (Pydantic BaseModel)
│   │   │   └── static/models.py      #       模型提供商静态定义
│   │   │
│   │   ├── agents/                   #     ★ LangGraph Agent 系统
│   │   │   ├── base.py               #       BaseAgent 抽象类
│   │   │   ├── state.py              #       BaseState 状态定义
│   │   │   ├── context.py            #       BaseContext 运行时配置
│   │   │   ├── buildin/              #       内置 Agent 实现
│   │   │   │   ├── __init__.py       #         AgentManager (自动发现)
│   │   │   │   ├── chatbot/          #         ChatbotAgent (通用对话)
│   │   │   │   └── deep_agent/       #         DeepAgent (深度推理)
│   │   │   ├── middlewares/          #     中间件链
│   │   │   │   ├── __init__.py
│   │   │   │   ├── knowledge_base_middleware.py
│   │   │   │   ├── skills_middleware.py
│   │   │   │   ├── attachment_middleware.py
│   │   │   │   └── ...
│   │   │   ├── toolkits/             #     工具包
│   │   │   │   ├── registry.py       #       工具注册
│   │   │   │   ├── buildin/tools.py  #       内置工具
│   │   │   │   ├── mysql/            #       MySQL 查询工具
│   │   │   │   └── kbs/              #       知识库查询工具
│   │   │   ├── backends/             #     后端存储抽象
│   │   │   │   ├── composite.py
│   │   │   │   ├── knowledge_base_backend.py
│   │   │   │   ├── skills_backend.py
│   │   │   │   └── sandbox/          #       沙箱后端
│   │   │   └── skills/buildin/       #     内置 Skills
│   │   │       ├── reporter/SKILL.md
│   │   │       └── deep-reporter/SKILL.md
│   │   │
│   │   ├── services/                 #     业务服务层
│   │   │   ├── chat_service.py       #       ★ 核心对话服务 (1102行)
│   │   │   ├── run_worker.py         #       ★ ARQ Worker 处理
│   │   │   ├── agent_run_service.py  #       Agent 运行生命周期
│   │   │   ├── run_queue_service.py  #       Redis 运行队列
│   │   │   ├── conversation_service.py
│   │   │   ├── mcp_service.py
│   │   │   ├── skill_service.py
│   │   │   ├── subagent_service.py
│   │   │   ├── tool_service.py
│   │   │   ├── evaluation_service.py
│   │   │   ├── langfuse_service.py
│   │   │   └── filesystem_*.py       #       多个文件系统服务
│   │   │
│   │   ├── repositories/             #     数据访问层 (SQLAlchemy ORM)
│   │   │   ├── agent_config_repository.py
│   │   │   ├── conversation_repository.py
│   │   │   ├── knowledge_base_repository.py
│   │   │   ├── user_repository.py
│   │   │   └── ... (12+ 仓库)
│   │   │
│   │   ├── storage/                  #     存储层
│   │   │   ├── postgres/             #       PostgreSQL
│   │   │   │   ├── manager.py        #         连接管理器
│   │   │   │   ├── models_business.py#         业务 ORM 模型
│   │   │   │   └── models_knowledge.py        # 知识 ORM 模型
│   │   │   └── minio/                #       MinIO 对象存储
│   │   │           ├── client.py
│   │   │           └── utils.py
│   │   │
│   │   ├── knowledge/                #     知识库引擎
│   │   │   ├── base.py               #       KnowledgeBase 抽象类
│   │   │   ├── manager.py            #       KnowledgeBaseManager
│   │   │   ├── factory.py            #       KnowledgeBaseFactory
│   │   │   ├── implementations/      #       具体实现
│   │   │   │   ├── lightrag.py       #         ★ LightRAG (779行)
│   │   │   │   ├── milvus.py         #         Milvus-only
│   │   │   │   └── dify.py           #         Dify 适配器
│   │   │   ├── chunking/             #       文档分块
│   │   │   │   └── ragflow_like/     #         RAGFlow 风格分块
│   │   │   └── graphs/               #       知识图谱
│   │   │       ├── adapters/
│   │   │       │   ├── base.py       #         GraphAdapter 抽象类
│   │   │       │   ├── lightrag.py   #         LightRAG 图适配器
│   │   │       │   ├── factory.py
│   │   │       │   └── upload.py
│   │   │       └── upload_graph_service.py    # 上传图服务 (778行)
│   │   │
│   │   ├── models/                   #     模型抽象层
│   │   ├── plugins/parser/           #     文档解析插件
│   │   │   ├── base.py               #       Parser ABC
│   │   │   ├── mineru.py             #       MinerU 解析
│   │   │   ├── pp_structure_v3.py    #       PaddleX OCR
│   │   │   ├── rapid_ocr.py          #       RapidOCR
│   │   │   ├── deepseek_ocr.py       #       DeepSeek OCR
│   │   │   ├── unified.py            #       统一解析门面
│   │   │   └── factory.py            #       解析器工厂
│   │   └── utils/                    #     通用工具
│   │
│   ├── pyproject.toml                #   项目配置 (uv + pytest)
│   └── test/                         #   测试
│       ├── unit/                     #     单元测试 (25+ 文件)
│       ├── integration/api/          #     集成测试 (14 文件)
│       └── e2e/                      #     端到端测试 (3 文件)
│
├── web/                              # Vue.js 前端
│   ├── src/
│   │   ├── main.js                   #     ★ 入口
│   │   ├── App.vue                   #     ★ 根组件
│   │   ├── router/index.js           #     路由配置
│   │   ├── apis/                     #     API 调用层 (17 模块)
│   │   │   ├── base.js               #       基础请求/错误处理
│   │   │   ├── agent_api.js
│   │   │   ├── auth_api.js
│   │   │   ├── graph_api.js
│   │   │   ├── knowledge_api.js
│   │   │   ├── mcp_api.js
│   │   │   ├── skill_api.js
│   │   │   └── ...
│   │   ├── stores/                   #     Pinia 状态管理
│   │   │   ├── agent.js              #       ★ Agent 状态
│   │   │   ├── user.js               #       用户认证
│   │   │   ├── theme.js              #       主题管理
│   │   │   ├── graphStore.js         #       图可视化状态
│   │   │   └── ...
│   │   ├── views/                    #     页面组件
│   │   │   ├── AgentView.vue         #       ★ 主对话界面
│   │   │   ├── HomeView.vue
│   │   │   ├── LoginView.vue
│   │   │   ├── GraphView.vue         #       知识图谱可视化
│   │   │   ├── DashboardView.vue     #       管理仪表盘
│   │   │   ├── DataBaseView.vue      #       数据库管理
│   │   │   └── ExtensionsView.vue    #       扩展管理
│   │   ├── components/               #     可复用组件 (80+)
│   │   │   ├── AgentPanel.vue        #       Agent 面板
│   │   │   ├── AgentChatComponent.vue#       对话组件
│   │   │   ├── AgentMessageComponent.vue
│   │   │   ├── AgentInputArea.vue
│   │   │   ├── AgentConfigSidebar.vue
│   │   │   ├── ToolCallingResult/    #       工具调用结果 (20+ 渲染器)
│   │   │   │   ├── AskUserQuestion.vue
│   │   │   │   ├── Calculator.vue
│   │   │   │   ├── Chart.vue
│   │   │   │   ├── EditFile.vue
│   │   │   │   ├── Execute.vue
│   │   │   │   ├── KnowledgeGraph.vue
│   │   │   │   ├── MySQL.vue
│   │   │   │   ├── ReadFile.vue
│   │   │   │   ├── WebSearch.vue
│   │   │   │   ├── WriteFile.vue
│   │   │   │   └── ...
│   │   │   ├── GraphCanvas.vue       #       图谱画布
│   │   │   ├── MindMapSection.vue    #       思维导图
│   │   │   ├── FileTreeComponent.vue #       文件树
│   │   │   ├── ModelProvidersComponent.vue
│   │   │   ├── ToolsManagerComponent.vue
│   │   │   ├── McpServersComponent.vue
│   │   │   ├── SkillsManagerComponent.vue
│   │   │   └── ...
│   │   ├── composables/              #     组合式函数
│   │   │   ├── useAgentStreamHandler.js
│   │   │   ├── useAgentRunStream.js
│   │   │   ├── useAgentThreadState.js
│   │   │   ├── useGraph.js
│   │   │   ├── useMention.js
│   │   │   ├── useApproval.js        #       人机审批流
│   │   │   └── useStreamSmoother.js  #       流输出平滑
│   │   └── utils/                    #     工具函数
│   ├── vite.config.js
│   └── package.json
│
├── docker/                           # Docker 配置
│   ├── api.Dockerfile                #   后端镜像 (Python 3.12 + uv)
│   ├── web.Dockerfile                #   前端镜像 (多阶段构建)
│   ├── nginx/                        #   Nginx 生产配置
│   └── sandbox_provisioner/          #   沙箱供给器
│
├── docker-compose.yml                # ★ 开发环境编排 (12+ 服务)
├── docker-compose.prod.yml           # ★ 生产环境编排
├── Makefile                          # 快捷命令 (up/down/format)
├── .env / .env.template              # 环境变量
│
├── docs/                             # VitePress 文档站点
│   ├── .vitepress/config.mts         #   文档导航配置
│   ├── index.md                      #   文档首页
│   ├── intro/                        #   入门指南
│   ├── agents/                       #   Agent 系统文档
│   ├── advanced/                     #   高级配置
│   └── develop-guides/               #   开发指南
│
└── scripts/                          # 初始化/拉取镜像脚本
```

---

## 四、关键代码解析

### 4.1 FastAPI 入口 (`backend/server/main.py`)

```python
# 核心启动逻辑
app = FastAPI(lifespan=lifespan)                    # 生命周期管理
app.include_router(router, prefix="/api")           # 所有路由统一挂载到 /api

# 中间件链
app.add_middleware(CORSMiddleware, allow_origins=["*"])
app.add_middleware(AccessLogMiddleware)             # 请求日志
app.add_middleware(LoginRateLimitMiddleware)        # 登录限流 (10次/60s)
app.add_middleware(AuthMiddleware)                  # 认证 (目前Token验证被注释)
```

**设计要点**:
- 所有路由统一通过 `server.routers.__init__.py` 聚合后挂载
- `LITE_MODE` 模式下跳过图谱/知识库/评估等重型路由
- `lifespan` 统一管理所有外部资源的初始化与清理

### 4.2 应用生命周期 (`backend/server/utils/lifespan.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段
    await init_postgres()           # PostgreSQL (业务 + LangGraph checkpoints)
    await init_mcp_servers()        # MCP 服务器连接
    await init_sub_agents()         # 子Agent加载
    await init_knowledge_manager()  # 知识库管理器
    await init_sandbox_provider()  # 沙箱提供者
    await init_tasker()             # 后台任务
    yield
    # 关闭阶段
    await cleanup_all()            # 清理所有资源
```

### 4.3 Agent 系统架构

#### BaseAgent 抽象类 (`backend/package/yuxi/agents/base.py`)

```python
class BaseAgent:
    """基础 Agent 抽象类，所有具体 Agent 都继承此类"""
    name = "base_agent"
    description = "base_agent"
    capabilities: list[str] = []
    context_schema: type[BaseContext] = BaseContext

    def __init__(self, **kwargs):
        self.graph = None               # LangGraph CompiledStateGraph
        self.checkpointer = None        # 对话历史持久化
        self.workdir = Path(save_dir) / "agents" / self.module_name
```

**持久化支持**:
- SQLite (默认，每个 Agent 独立 `aio_history.db`)
- PostgreSQL (`AsyncPostgresSaver`，生产环境)
- InMemorySaver (测试环境)

#### ChatbotAgent (`backend/package/yuxi/agents/buildin/chatbot/graph.py`)

```python
# 中间件链 (按执行顺序)
middlewares = [
    FilesystemMiddleware(...),              # 1. 沙箱文件系统访问
    save_attachments_to_fs,                 # 2. 附件注入
    KnowledgeBaseMiddleware(),              # 3. 知识库查询工具
    RuntimeConfigMiddleware(...),           # 4. 运行时配置 (模型/工具/MCP/提示词)
    SkillsMiddleware(),                     # 5. Skills 提示词注入 + 动态激活
    SubAgentMiddleware(...),                # 6. 子Agent委派
    SummaryOffloadMiddleware(...),          # 7. 上下文压缩 (90k tokens 触发)
    TodoListMiddleware(...),                # 8. 待办事项跟踪
    PatchToolCallsMiddleware(),             # 9. 工具调用修补
    ModelRetryMiddleware(),                 # 10. 模型失败重试
]
```

#### DeepAgent (深度推理Agent)

- 基于 Tavily 网络搜索
- ToolCallLimitMiddleware: 每线程 20 次搜索调用 / 每次运行 50 次总工具调用
- SummaryOffloadMiddleware: 90k tokens 触发上下文压缩
- 支持规划和子Agent协作

### 4.4 LightRAG 知识库 (`backend/package/yuxi/knowledge/implementations/lightrag.py`)

```python
class LightRagKB:
    """LightRAG 知识库实现，融合向量检索与知识图谱"""

    # 存储后端配置
    vector_storage = MilvusVectorDBStorage    # Milvus 向量存储
    graph_storage = Neo4JStorage              # Neo4j 图存储
    kv_storage = JsonKVStorage                # JSON KV存储
    doc_status = JsonDocStatusStorage         # 文档状态跟踪

    # 检索模式
    async def query(self, query_text: str) -> dict:
        return await self.rag.aquery_data(
            query=query_text,
            param=QueryParam(mode="mix")  # 向量 + 图谱混合检索
        )
```

**文件索引流程**:
1. 文档解析 → Markdown (MinerU/PaddleX/DeepSeek OCR)
2. RAGFlow 风格分块 → 语义分块
3. `rag.ainsert()` → 向量化 + 图谱构建
4. 实例缓存按 `db_id` 隔离，LLM 模型变更时自动失效

### 4.5 知识图谱双系统

项目中有**两套并行的图谱系统**:

| 系统 | 来源 | 文件 | 说明 |
|------|------|------|------|
| LightRAG 图 | 文档自动生成 | `graphs/adapters/lightrag.py` | 从文档提取实体关系，自动构建 |
| 上传图 | 手动上传三元组 | `graphs/upload_graph_service.py` | JSONL 三元组上传，向量相似度 + 模糊匹配 |

```python
# 上传图服务核心逻辑
class UploadGraphService:
    async def upload_jsonl(self, minio_url: str):
        # 1. 解析 JSONL 三元组 (subject, predicate, object)
        # 2. 在 Neo4j 创建实体 (Entity:Upload 标签)
        # 3. 计算向量嵌入并存储到节点
        # 4. 持久化 graph_info.json

    async def query(self, query_text: str, config: GraphQueryConfig):
        # 1. 查询文本向量化
        # 2. Neo4j 余弦相似度搜索
        # 3. 模糊名称匹配兜底
        # 4. 2 跳子图扩展
        # 5. 返回规范化节点/边
```

### 4.6 ARQ 异步任务队列

```python
# Worker 入口 (backend/server/worker_main.py)
# ARQ Worker 配置在 yuxi.services.run_worker 中
class WorkerSettings:
    functions = [process_agent_run]   # 核心处理函数

# 任务流程:
# 1. chat_service.py 将 Agent 运行入队 (Redis)
# 2. Worker 消费任务, 调用 Agent.invoke()
# 3. 事件通过 ChunkedEventWriter 写入 Redis 事件流
# 4. 前端通过 SSE 订阅 Redis 事件流
# 5. 支持取消信号 (Redis key)
```

### 4.7 对话服务核心 (`backend/package/yuxi/services/chat_service.py`)

```python
# 核心函数 (~1102 行)
async def stream_agent_chat(...) -> AsyncGenerator:
    """流式 Agent 对话，编排 LangGraph 流式输出"""
    # 1. 获取 Agent 实例
    # 2. 构建运行时上下文
    # 3. 调用 agent.stream_messages()
    # 4. 处理 LangGraph 事件流 (tool_call, tool_result, ai_message)
    # 5. 格式化为前端可消费的 SSE 事件
    # 6. 持久化对话历史
```

### 4.8 前端核心架构

#### 路由配置 (`web/src/router/index.js`)

```javascript
// 主要路由
const routes = [
  { path: '/', component: HomeView },
  { path: '/login', component: LoginView },
  { path: '/agent', component: AgentView, meta: { requiresAuth: true } },
  { path: '/graph', component: GraphView, meta: { requiresAuth: true, requiresAdmin: true } },
  { path: '/database', component: DataBaseView, meta: { requiresAdmin: true } },
  { path: '/dashboard', component: DashboardView, meta: { requiresAdmin: true } },
  { path: '/extensions', component: ExtensionsView, meta: { requiresSuperAdmin: true } },
];
```

#### Agent 状态管理 (`web/src/stores/agent.js`)

```javascript
// Pinia store, 使用 persistedstate 持久化
defineStore('agent', {
  state: () => ({
    agentsList: [],           // 可用 Agent 列表
    selectedAgent: null,      // 当前选中 Agent
    agentConfigs: {},         // Agent 配置
    knowledgeBases: [],       // 知识库列表
    mcps: [],                 // MCP 服务器
    skills: [],               // 已安装 Skills
  }),
  // 持久化 selectedAgent 和 config
});
```

#### 流式对话处理 (`web/src/composables/`)

```
useAgentStreamHandler.js   → 处理 SSE 流式响应
useAgentRunStream.js       → 处理异步 Agent 运行流
useAgentThreadState.js     → 管理对话线程状态
useApproval.js             → 人机审批流 (Human-in-the-loop)
useStreamSmoother.js       → 流输出平滑 (打字机效果)
```

---

## 五、Docker Compose 服务拓扑

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose (开发)                         │
│                                                                     │
│  业务服务:                                                           │
│  ┌──────┐    ┌────────┐    ┌───────────────────┐                   │
│  │ api  │──→ │ worker │    │ sandbox-provisioner│                   │
│  │:5050 │    │(ARQ)   │    │      :8002         │                   │
│  └──┬───┘    └───┬────┘    └───────────────────┘                   │
│     │            │                                                  │
│  基础设施:                                                          │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐                │
│  │postgres│ │redis │  │neo4j │  │milvus│  │minio │                │
│  │ :5432 │  │ :6379│  │:7687 │  │:19530│  │ :9000│                │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘                │
│                                                                     │
│  文档解析 (GPU, 可选):                                               │
│  ┌──────────────────┐  ┌────────────┐  ┌────────────┐              │
│  │mineru-vllm-server│  │ mineru-api │  │  paddlex   │              │
│  │    :30000         │  │  :30001    │  │   :8080    │              │
│  └──────────────────┘  └────────────┘  └────────────┘              │
│                                                                     │
│  前端:                                                              │
│  ┌──────┐                                                          │
│  │ web  │  :5173 (Vite Dev Server)                                  │
│  └──────┘                                                          │
└─────────────────────────────────────────────────────────────────────┘
```

**服务职责说明**:

| 服务 | 端口 | 职责 |
|------|------|------|
| api | 5050 | FastAPI 开发服务器 (热重载) |
| worker | - | ARQ 异步任务 Worker |
| sandbox-provisioner | 8002 | 沙箱执行环境 (Docker 容器隔离) |
| web | 5173 | Vue/Vite 开发服务器 (热重载) |
| postgres | 5432 | 关系数据库 (业务 + 知识元数据 + LangGraph checkpoint) |
| redis | 6379 | 任务队列 + 事件流 + 缓存 |
| neo4j | 7474/7687 | 知识图谱数据库 |
| milvus | 19530 | 向量数据库 (RAG 检索) |
| minio | 9000/9001 | 对象存储 (文件/附件) |
| etcd | - | Milvus 元数据协调 |

---

## 六、核心设计模式与架构不变量

### 6.1 分层架构

```
HTTP 请求流:
Request → Router (路由匹配) → Service (业务逻辑) → Repository (数据访问) → DB
```

**关键原则**:
- **路由层是薄的**: HTTP 路由只负责参数提取和响应格式化，业务逻辑在 `yuxi.services`
- **持久层抽象**: 数据访问集中在 `yuxi.repositories`，使用 SQLAlchemy ORM
- **前端 API 集中管理**: 所有 API 调用集中在 `web/src/apis/`

### 6.2 Agent 能力组合化

Agent 的能力不是硬编码的，而是通过以下层次动态组合:

```
Agent 能力 = Context(配置) + Middleware(中间件) + Toolkits(工具) + Backends(后端) + Skills(技能)
```

- **Context**: 运行时配置 (模型、工具开关、知识库绑定)
- **Middleware**: 处理链 (文件系统、知识库、摘要、子Agent委派)
- **Toolkits**: 可用工具集 (搜索、数据库、知识库查询)
- **Backends**: 存储后端 (沙箱文件系统、知识库存储)
- **Skills**: 动态激活的专业技能 (报告生成、深度分析)

### 6.3 LITE_MODE

通过 `LITE_MODE=true` 环境变量可以跳过重型组件:
- 跳过知识图谱路由 (`graph_router.py`)
- 跳过知识库路由 (`knowledge_router.py`)
- 跳过评估路由 (`evaluation_router.py`)
- 跳过思维导图路由 (`mindmap_router.py`)

适用于只需要基础对话能力的轻量部署场景。

### 6.4 沙箱隔离

```
SANDBOX_VIRTUAL_PATH_PREFIX: /home/gem/user-data
SANDBOX_PROVIDER: provisioner  # Docker 容器隔离
SANDBOX_EXEC_TIMEOUT_SECONDS: 180
```

文件操作通过沙箱供给器执行，确保代码执行工具 (如 `Execute`) 在隔离的 Docker 容器中运行，无法访问宿主机文件系统。

---

## 七、数据流关键链路

### 7.1 对话请求链路

```
前端 (AgentView.vue)
  → POST /api/chat/agent
  → chat_router.py (接收请求)
  → chat_service.py (编排对话)
  → AgentManager.get_agent() (获取Agent实例)
  → BaseAgent.stream_messages() (LangGraph 流式执行)
     → Middleware 链执行
     → LLM 调用 (OpenAI 兼容接口)
     → 工具调用 (搜索/知识库/沙箱/MCP)
  → SSE 流式返回到前端
  → AgentMessageComponent 渲染
```

### 7.2 异步任务链路

```
前端发起长任务
  → POST /api/chat/runs
  → run_queue_service.py (入队到 Redis)
  → worker (ARQ 消费)
  → run_worker.py (process_agent_run)
     → Agent.invoke() 执行
     → ChunkedEventWriter 写入 Redis 事件流
  → 前端 GET /api/chat/runs/{run_id}/events (SSE 订阅)
  → 支持取消: Redis key 信号
```

### 7.3 知识库检索链路

```
上传文档
  → knowledge_router.py
  → 文档解析 (MinerU/PaddleX/DeepSeek OCR)
  → RAGFlow 风格分块
  → LightRAG.ainsert()
     → Milvus: 存储向量分块
     → Neo4j: 存储实体关系

用户查询
  → KnowledgeBaseMiddleware (Agent 内部)
  → LightRAG.aquery_data(mode="mix")
     → Milvus: 向量相似度检索
     → Neo4j: 图谱关系检索
  → 合并结果返回给 LLM
```

---

## 八、测试策略

```
backend/test/
├── unit/                    # 单元测试 (25+ 文件)
│   ├── test_*.py            #   独立模块测试
│   └── ...
├── integration/api/         # 集成测试 (14 文件)
│   ├── test_chat_*.py       #   API 路由集成测试
│   └── ...
└── e2e/                     # 端到端测试 (3 文件)
    ├── test_agent_*.py      #   完整 Agent 流程测试
    └── ...
```

**测试框架**: pytest + pytest-asyncio + pytest-httpx + pytest-cov
**标记**: `unit`, `integration`, `e2e`, `auth`, `slow`
**配置**: `asyncio_mode = "auto"` (pyproject.toml)

---

## 九、配置系统

### 9.1 后端配置 (`backend/package/yuxi/config/`)

```python
# 配置加载链
.env 文件 → Config 单例 (Pydantic BaseModel) → saves/config/base.toml
```

核心配置项:
- `default_model`: 默认 LLM 模型
- `fast_model`: 快速模型 (用于摘要等)
- `embed_model`: 嵌入模型
- `reranker`: 重排序模型
- `model_providers`: 模型提供商注册表
- `custom_providers.toml`: 自定义提供商配置

### 9.2 前端配置

```javascript
// web/.env
VITE_API_URL=http://localhost:5050    // API 地址
VITE_APP_TITLE=Yuxi                   // 应用标题
```

---

## 十、文档体系

文档站点基于 **VitePress** 构建，部署在 `docs/` 目录下。

| 分组 | 路径 | 内容 |
|------|------|------|
| 入门 | `docs/intro/` | 项目概览、快速开始、模型配置、知识库、评估 |
| Agent | `docs/agents/` | Agent配置、Langfuse集成、MCP、中间件、沙箱、Skills、子Agent、工具 |
| 高级 | `docs/advanced/` | API Key集成、品牌定制、配置、部署、文档处理、第三方认证 |
| 开发 | `docs/develop-guides/` | 更新日志、贡献指南、设计规范、路线图、测试指南 |

导航配置定义在 `docs/.vitepress/config.mts` 中。
