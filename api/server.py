"""
FastAPI 法律智能问答 API 服务

启动：
    python api/server.py
    访问 http://localhost:8000/docs 查看 Swagger UI

端点：
    POST /chat     - 多 Agent 问答
    POST /search   - 纯检索（不调用 LLM）
    GET  /health   - 健康检查
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.orchestrator import AgentOrchestrator
from agents.tools import get_retriever
from rag.prompts import build_context_text

app = FastAPI(
    title="法律智能问答 API",
    description="基于本地 LLM + LangChain 多 Agent + FAISS 向量检索的法律问答系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 延迟初始化
_orchestrator = None


def get_orchestrator(model: str = "qwen2.5:3b"):
    global _orchestrator
    if _orchestrator is None or _orchestrator.model != model:
        _orchestrator = AgentOrchestrator(model=model)
    return _orchestrator



# ==================== 请求/响应模型 ====================

class ChatRequest(BaseModel):
    question: str = Field(..., description="法律问题", min_length=1, max_length=1000)
    mode: str = Field("sequential", description="模式: sequential/parallel/hierarchical")
    model: str = Field("qwen2.5:3b", description="Ollama 模型名")
    session_id: str = Field("default", description="会话ID，用于隔离多用户对话历史")


class SearchRequest(BaseModel):
    query: str = Field(..., description="检索查询词")
    top_k: int = Field(5, description="返回条数", ge=1, le=20)


class ChatResponse(BaseModel):
    question: str
    answer: str
    mode: str
    model: str


class SearchResult(BaseModel):
    title: str
    article_no: str
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class HealthResponse(BaseModel):
    status: str
    index_size: int
    index_dim: int


# ==================== 端点 ====================

@app.get("/health", response_model=HealthResponse)
def health():
    r = get_retriever()
    return HealthResponse(
        status="ok",
        index_size=r.ntotal,
        index_dim=r.dim,
    )


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    r = get_retriever()
    chunks, scores = r.search(req.query, top_k=req.top_k)
    results = [
        SearchResult(
            title=c.get("title", ""),
            article_no=c.get("article_no", ""),
            content=c.get("content", ""),
            score=s,
        )
        for c, s in zip(chunks, scores)
    ]
    return SearchResponse(query=req.query, results=results)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    orch = get_orchestrator(model=req.model)
    answer = orch.chat(req.question, session_id=req.session_id, mode=req.mode)
    return ChatResponse(
        question=req.question,
        answer=answer,
        mode=req.mode,
        model=req.model,
    )


@app.post("/clear_session")
def clear_session(session_id: str = "default"):
    """清空指定会话的后端对话历史"""
    orch = get_orchestrator()
    orch.clear_session(session_id)
    return {"status": "ok", "session_id": session_id}



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
