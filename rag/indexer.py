"""
FAISS 索引构建与加载模块
"""
import json
import faiss
import numpy as np
from pathlib import Path
from typing import List, Dict

from rag.embeddings import EmbeddingModel


class FaissIndexer:
    """基于 FAISS 的向量索引"""

    def __init__(self, embedding_model: EmbeddingModel):
        self.embedding_model = embedding_model
        self.index = None
        self.metadata: List[Dict] = []

    def build(
        self,
        segments: List[Dict],
        batch_size: int = 32,
    ) -> "FaissIndexer":
        """
        根据文本分段构建 FAISS 索引
        :param segments: 分段列表，优先使用 embedding_text 字段（如果有），
                         否则使用 content 字段
        :param batch_size: 编码批次大小
        """
        if not segments:
            raise ValueError("segments 不能为空")

        # 优先使用 embedding_text（chunker v2 提供），否则 fallback 到 content
        texts = [seg.get("embedding_text", seg.get("content", "")) for seg in segments]
        embeddings = self.embedding_model.encode(
            texts, batch_size=batch_size, show_progress=True
        )
        dim = embeddings.shape[1]

        # 使用 IndexFlatIP：若向量已归一化，内积等价于余弦相似度
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings)
        self.metadata = segments

        return self

    def save(self, vector_dir: Path, index_name: str = "npc") -> None:
        """保存索引和元数据"""
        vector_dir = Path(vector_dir)
        vector_dir.mkdir(parents=True, exist_ok=True)

        index_path = vector_dir / f"{index_name}.faiss"
        metadata_path = vector_dir / f"{index_name}_metadata.json"

        faiss.write_index(self.index, str(index_path))
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def load(self, vector_dir: Path, index_name: str = "npc") -> "FaissIndexer":
        """加载索引和元数据"""
        vector_dir = Path(vector_dir)
        index_path = vector_dir / f"{index_name}.faiss"
        metadata_path = vector_dir / f"{index_name}_metadata.json"

        if not index_path.exists():
            raise FileNotFoundError(f"索引文件不存在: {index_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"元数据文件不存在: {metadata_path}")

        self.index = faiss.read_index(str(index_path))
        with open(metadata_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        return self

    @property
    def dim(self) -> int:
        """索引维度"""
        if self.index is None:
            return 0
        return self.index.d

    @property
    def ntotal(self) -> int:
        """索引中向量总数"""
        if self.index is None:
            return 0
        return self.index.ntotal


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import EMBEDDING_CONFIG, VECTOR_DIR

    embedder = EmbeddingModel(
        model_name=EMBEDDING_CONFIG["model_name"],
        device=EMBEDDING_CONFIG["device"],
        normalize_embeddings=EMBEDDING_CONFIG["normalize_embeddings"],
    )
    indexer = FaissIndexer(embedder)
    indexer.load(VECTOR_DIR, index_name="npc")
    print(f"索引维度: {indexer.dim}, 向量数: {indexer.ntotal}")
