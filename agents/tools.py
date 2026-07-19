"""
Agent 可用工具 —— LangChain @tool 实现

- law_search: 检索 FAISS 法律条文，返回统一格式（复用 prompts.build_context_text）
- 共享检索器单例（api / agent / evaluation 共用，避免重复加载 embedding 模型）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.tools import tool

from rag.prompts import build_context_text

_retriever = None


def get_retriever():
    """获取共享的检索器单例（api 和 agent 共用，避免重复加载模型）"""
    global _retriever
    if _retriever is None:
        from rag.retriever import FaissRetriever
        _retriever = FaissRetriever()
    return _retriever


@tool
def law_search(query: str) -> str:
    """Search Chinese laws and regulations database.
    Input should be a legal-related query in Chinese
    (e.g. 试用期最长多久, 劳动合同解除条件).
    Returns the most relevant legal articles with full text and citations.
    """
    if not query or not query.strip():
        return "错误：未提供检索查询"
    retriever = get_retriever()
    chunks, scores = retriever.search(query, top_k=5)
    if not chunks:
        return "未检索到相关法条"
    # 复用 prompts.py 的统一格式，保证法条格式一致
    return "以下是与查询相关的法律条文：\n\n" + build_context_text(chunks)
