"""
FAISS 检索器（v2：支持同法条折叠去重）

用法：
    retriever = FaissRetriever()
    chunks, scores = retriever.search("试用期最长可以约定多久？", top_k=5)

检索策略：
1. 从 FAISS 检索 2×top_k 条候选
2. 按 parent_article_id 折叠同法条的 chunk，合并内容，保留最高分
3. 去重排序，截取 top_k 返回
"""
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import VECTOR_DIR, VECTOR_CONFIG, EMBEDDING_CONFIG
from rag.embeddings import EmbeddingModel
from rag.indexer import FaissIndexer


class FaissRetriever:
    """FAISS 法律条文检索器"""

    def __init__(
        self,
        index_name: str = "npc",
        top_k: int = None,
    ):
        self.index_name = index_name
        self.top_k = top_k or VECTOR_CONFIG.get("top_k", 5)
        self.embedder = EmbeddingModel(
            model_name=EMBEDDING_CONFIG["model_name"],
            device=EMBEDDING_CONFIG["device"],
            normalize_embeddings=EMBEDDING_CONFIG["normalize_embeddings"],
        )
        self.indexer = FaissIndexer(self.embedder)
        self.indexer.load(VECTOR_DIR, index_name=index_name)

    def search(self, query: str, top_k: int = None) -> Tuple[List[dict], List[float]]:
        """
        检索与 query 最相关的法条 chunk（带同法条折叠）
        :return: (chunks, scores)
        """
        top_k = top_k or self.top_k
        fetch_k = top_k * 2  # 多取一些，折叠后还能凑够 top_k

        query_vec = self.embedder.encode([query])
        scores, ids = self.indexer.index.search(query_vec, fetch_k)

        # 收集所有命中 chunk
        raw_chunks = []
        raw_scores = []
        for idx, score in zip(ids[0], scores[0]):
            if idx < 0 or idx >= len(self.indexer.metadata):
                continue
            raw_chunks.append(self.indexer.metadata[idx])
            raw_scores.append(float(score))

        # 按 parent_article_id 折叠：同一条法的 chunk 合并
        folded = self._fold_by_article(raw_chunks, raw_scores)

        # 截取 top_k
        folded = folded[:top_k]
        chunks = [item["chunk"] for item in folded]
        score_list = [item["score"] for item in folded]

        return chunks, score_list

    def _fold_by_article(self, chunks: List[dict], scores: List[float]) -> List[dict]:
        """
        按 parent_article_id 折叠同法条 chunk
        - 同一 parent_article_id 只保留一条
        - 内容合并（用分隔符区分不同 chunk）
        - 分数取最高分
        """
        groups = {}  # parent_id → {chunks, scores, best_score, best_idx}

        for chunk, score in zip(chunks, scores):
            pid = chunk.get("parent_article_id", "")
            if not pid:
                # 没有 parent_article_id 的，用 (title, article_no) 当 key
                pid = f"{chunk.get('title', '')}__{chunk.get('article_no', '')}"

            if pid not in groups:
                groups[pid] = {
                    "chunks": [],
                    "scores": [],
                    "best_score": -999,
                    "best_idx": 0,
                }
            g = groups[pid]
            g["chunks"].append(chunk)
            g["scores"].append(score)
            if score > g["best_score"]:
                g["best_score"] = score
                g["best_idx"] = len(g["chunks"]) - 1

        # 构建折叠后的结果
        result = []
        for pid, g in groups.items():
            best_chunk = g["chunks"][g["best_idx"]]

            if len(g["chunks"]) == 1:
                merged = best_chunk.copy()
            else:
                # 合并同法条所有 chunk 的内容（去重后拼接）
                merged = best_chunk.copy()
                seen_content = {best_chunk.get("content", "")}
                extra_parts = []
                for i, c in enumerate(g["chunks"]):
                    ct = c.get("content", "")
                    if ct and ct not in seen_content:
                        seen_content.add(ct)
                        extra_parts.append(ct)
                if extra_parts:
                    merged["content"] = merged.get("content", "") + "\n" + "\n".join(extra_parts)
                merged["chunk_total"] = max(best_chunk.get("chunk_total", 1), len(g["chunks"]))
                merged["folded_count"] = len(g["chunks"])

            result.append({
                "chunk": merged,
                "score": g["best_score"],
            })

        # 按分数降序
        result.sort(key=lambda x: x["score"], reverse=True)
        return result

    def search_formatted(self, query: str, top_k: int = None) -> List[str]:
        """返回格式化的检索结果"""
        chunks, scores = self.search(query, top_k)
        lines = []
        for i, (chunk, score) in enumerate(zip(chunks, scores), 1):
            folded = f" (折叠{chunk.get('folded_count', 1)}块)" if chunk.get("folded_count", 1) > 1 else ""
            lines.append(
                f"[{i}] {chunk['title']} {chunk['article_no']}"
                f" (相关度: {score:.4f}){folded}"
            )
            lines.append(f"    {chunk['content'][:150]}...")
            lines.append("")
        return lines

    @property
    def dim(self) -> int:
        return self.indexer.dim

    @property
    def ntotal(self) -> int:
        return self.indexer.ntotal


if __name__ == "__main__":
    retriever = FaissRetriever()
    print(f"索引: {retriever.ntotal} 条向量, 维度 {retriever.dim}")
    for line in retriever.search_formatted("试用期最长可以约定多久？", top_k=5):
        print(line)
