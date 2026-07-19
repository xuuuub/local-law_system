"""
验证 FAISS 索引是否可用
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from config import VECTOR_DIR, EMBEDDING_CONFIG
from rag.embeddings import EmbeddingModel
from rag.indexer import FaissIndexer


def main():
    print("=== 验证 FAISS 索引 ===")

    # 1. 直接读取索引
    indexer = FaissIndexer(None)
    indexer.load(VECTOR_DIR, index_name="npc")
    print(f"索引维度: {indexer.dim}")
    print(f"向量总数: {indexer.ntotal}")

    # 2. 加载 embedding 模型
    embedder = EmbeddingModel(
        model_name=EMBEDDING_CONFIG["model_name"],
        device=EMBEDDING_CONFIG["device"],
        normalize_embeddings=EMBEDDING_CONFIG["normalize_embeddings"],
    )
    print(f"Embedding 模型: {embedder.model_name}, 维度: {embedder.dim}")

    # 3. 测试检索
    query = "试用期最长可以约定多久？"
    query_vec = embedder.encode([query])
    scores, ids = indexer.index.search(query_vec, 3)

    print(f"\n查询: {query}")
    print(f"Top-3 索引 ID: {ids[0].tolist()}")
    print(f"相似度分数: {scores[0].tolist()}")

    for rank, idx in enumerate(ids[0]):
        seg = indexer.metadata[idx]
        chunk_info = ""
        if seg.get("chunk_total", 1) > 1:
            chunk_info = f" [{seg.get('chunk_index', 0) + 1}/{seg['chunk_total']}]"
        print(f"\n--- 第 {rank + 1} 条 ---")
        print(f"标题: {seg['title']} {seg['article_no']}{chunk_info}")
        print(f"类型: {seg.get('chunk_type', 'whole')}, 分数: {scores[0][rank]:.4f}")
        print(f"内容: {seg['content'][:120]}...")
        # 如果 embedding_text 与 content 不同，说明经过了扩写
        et = seg.get("embedding_text", "")
        if et and et != seg.get("content", ""):
            print(f"向量文本: {et[:120]}...")




if __name__ == "__main__":
    main()
