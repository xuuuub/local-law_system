"""
文本向量化模块
封装 sentence-transformers，提供统一的 encode 接口
"""
import numpy as np
from typing import List, Union
from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    """基于 sentence-transformers 的向量化模型"""

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        normalize_embeddings: bool = True,
    ):
        """
        :param model_name: HuggingFace 模型名称，如 BAAI/bge-small-zh-v1.5
        :param device: cpu 或 cuda
        :param normalize_embeddings: 是否对向量做 L2 归一化
        """
        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        self.model = SentenceTransformer(model_name, device=device)

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """
        将文本编码为向量
        :return: shape=(N, dim) 的 float32 numpy 数组
        """
        if isinstance(texts, str):
            texts = [texts]

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize_embeddings,
        )
        return embeddings.astype(np.float32)

    @property
    def dim(self) -> int:
        """获取向量维度"""
        # sentence-transformers >= 5.x 使用 get_embedding_dimension
        if hasattr(self.model, "get_embedding_dimension"):
            return self.model.get_embedding_dimension()
        return self.model.get_sentence_embedding_dimension()



if __name__ == "__main__":
    from config import EMBEDDING_CONFIG

    embedder = EmbeddingModel(
        model_name=EMBEDDING_CONFIG["model_name"],
        device=EMBEDDING_CONFIG["device"],
        normalize_embeddings=EMBEDDING_CONFIG["normalize_embeddings"],
    )
    print(f"模型: {embedder.model_name}, 维度: {embedder.dim}")
    vec = embedder.encode("试用期的最长约定时间是六个月。")
    print(f"向量 shape: {vec.shape}")
    print(f"向量模长: {np.linalg.norm(vec):.6f}")
