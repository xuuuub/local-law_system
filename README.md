# 基于本地大语言模型的法律法规智能问答系统

## 项目简介

完全本地化的法律法规智能问答系统，四层架构：

| 层级 | 技术 | 说明 |
|------|------|------|
| 数据 | 自爬 84 部法律 + FAISS | 8798 条分段，8835 向量 |
| 检索 | bge-large-zh-v1.5（1024维） | 语义检索 + 同法条折叠去重 |
| 生成 | Ollama + qwen2.5 | 本地推理，3b/7b/14b 随意切 |
| 调度 | LangChain 多 Agent | 检索Agent / 问答Agent / 总结Agent |

**全程离线**，数据、向量索引、大模型都在本地。

---

## 系统流程

```
用户问题
    │
    ▼
┌─ Agent 调度层（LangChain）────────────────────────┐
│  sequential:   串行（检索Agent → 问答Agent）      │
│  parallel:     并行（拆子问题→多检索→汇总）       │
│  hierarchical: 合作（调度Agent + 3 子Agent）      │
└──────────────────────┬───────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
检索Agent          问答Agent          总结Agent
(FAISS搜索)        (法条→答案)        (法条→摘要)
    │                  │                  │
    └──────────────────┴──────────────────┘
                       │
                       ▼
              带引用来源的最终回答
```

---

## 项目结构

```
demo1/
├── config.py                # 全局配置
├── requirements.txt
│
├── crawler/                 # 数据爬取
│   ├── npc_crawler.py       #   国家法律法规数据库爬虫
│   ├── cleaner.py           #   清洗分段 + 类型过滤
│   └── utils.py
│
├── rag/                     # 向量化 + 检索 + LLM
│   ├── embeddings.py        #   bge-large-zh-v1.5 编码（CPU）
│   ├── indexer.py           #   FAISS 索引构建
│   ├── chunker.py           #   法条分块（长拆 + 短扩）
│   ├── retriever.py         #   向量检索 + 同法条折叠
│   └── prompts.py           #   Prompt 模板（Agent 共用）
│
├── agents/                  # 多 Agent 协作（LangChain）
│   ├── tools.py             #   law_search 工具（@tool，单例检索器）
│   └── orchestrator.py      #   LangChain 编排器（三模式）
│
├── api/                     # Web 服务
│   └── server.py            #   FastAPI（启动时预加载索引）
│
├── frontend/
│   └── streamlit_app.py     #   Streamlit 前端
│
├── evaluation/              # 测试评估
│   ├── test_questions.json  #   100 条标注问题
│   └── test_results.json         #   测试结果
│
├── scripts/
│   ├── run_crawler.py       #   爬虫入口
│   ├── build_index.py       #   构建索引
│   ├── verify_index.py      #   索引验证
│   ├── test_agents.py       #   Agent 测试
│   ├── test_api.py          #   API 测试
│   └── run_api.py           #   API 启动入口
│
├── data/
│   ├── raw/npc/             #   爬虫原始 JSON+TXT
│   ├── processed/           #   segments + chunks
│   └── vectors/             #   FAISS 索引文件
│
└── logs/
```

---

## 需求对照

### 串行模式（sequential）
**对应需求**："构造基础Agent组合：检索Agent，问答Agent"

在 `agents/orchestrator.py` `_run_sequential`：
- 检索 Agent（ReAct + law_search 工具）→ 拿法条
- 问答 Agent（LCEL chain + `QA_TASK_TEMPLATE`）→ 生成带引用的答案
- Prompt 统一管理在 `rag/prompts.py`

### 并行模式（parallel）
**对应需求**："实现串行/并行/合作三种 agent 模式"

在 `agents/orchestrator.py` `_run_parallel`：
- LLM 拆问题为 2~3 个子关键词
- `ThreadPoolExecutor` 并发检索（真并行）
- 问答 Agent 汇总多路法条生成答案

### 合作模式（hierarchical）
**对应需求**："多Agent协作任务调用"

在 `agents/orchestrator.py` `_run_hierarchical`：
- 调度 Agent（ReAct）把 检索/问答/总结 包装成 3 个工具
- LLM 自主决策调用哪个子 Agent，体现 Agent 间合作

### 多轮对话
**对应需求**："支持问题维持上下文"

在 `agents/orchestrator.py` 第 176 行 `chat()` 方法：
- `session_id` 维持对话历史（最近 3 轮）
- 前后端通过 session 传递上下文

---

## 各阶段说明

### 第一阶段：数据爬取
- 84 部核心法律，8798 条分段
- 只保留宪法+法律，过滤地方法规/司法解释/案例
- 覆盖：宪法、民法典、刑法、三大诉讼法、劳动法、行政法、公司法、知识产权、经济法等

### 第二阶段：分块 + 向量化
- 长法条(>500字)按项/句拆分，保留法条前缀
- 短法条(<150字)扩写上下文增强语义
- bge-large-zh-v1.5，1024维，8835条向量
- embedding 模型放 CPU（省 GPU 给 LLM）

### 第三阶段：RAG 问答核心（多Agent协作）
- 用户问题 → FAISS检索 → Prompt → Ollama → 答案+引用
- 同法条折叠去重，避免重复浪费上下文

### 第四阶段：多 Agent 协作（LangChain）
- 三个 Agent：检索 / 问答 / 总结
- 三种模式：串行 / 并行 / 合作
- 检索 Agent 与调度 Agent 用 ReAct，问答/总结 Agent 用 LCEL chain
- Prompt 统一管理在 `rag/prompts.py`

### 第五阶段：FastAPI + Streamlit 前端
- `/chat` `/search` `/health` 三个 RESTful 端点
- 启动时预加载索引，后续请求秒响应
- Swagger UI 自动生成接口文档
- Streamlit 前端支持模型切换和模式选择

### 第六阶段：测试数据集
- 102 条标注问题，覆盖 10 个法律类别
- 批量评估脚本自动填充 retrieved_text + model_output

---

## 快速开始

### 环境
- Python 3.13
- NVIDIA GPU（可选）
- [Ollama](https://ollama.com) 桌面版

### 安装
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b    # 推荐
ollama pull qwen2.5:14b
```

### 启动
```bash

#如果是在win的cmd中
cd /d 自己存放项目地址

#运行了setup.bat配置好了对应环境后
conda activate law

#启动如下

# 终端1：API
python scripts/run_api.py

# 终端2：前端
streamlit run frontend/streamlit_app.py
```

访问 `http://localhost:8501` 使用前端，`http://localhost:8000/docs` 测试 API。

### 更新法条
```bash
python scripts/run_crawler.py --source npc --type law --keywords 新法名 --max 10
python scripts/build_index.py
```

---

## 开发计划

- [x] 第一阶段：数据爬取
- [x] 第二阶段：向量化 + FAISS 索引
- [x] 第三阶段：RAG 问答核心
- [x] 第四阶段：多 Agent 协作（LangChain）
- [x] 第五阶段：FastAPI + Streamlit 前端
- [x] 第六阶段：测试数据集
