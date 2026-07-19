"""
构建 FAISS 向量索引的入口脚本
用法：
    python scripts/build_index.py
    python scripts/build_index.py --source npc --model BAAI/bge-large-zh-v1.5 --batch-size 16
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json
from config import PROCESSED_DIR, VECTOR_DIR, EMBEDDING_CONFIG
from crawler.utils import setup_logger
from rag.embeddings import EmbeddingModel
from rag.indexer import FaissIndexer
from rag.chunker import LegalChunker

logger = setup_logger("build_index")


def main():
    parser = argparse.ArgumentParser(description="构建法律法规 FAISS 向量索引")
    parser.add_argument(
        "--source",
        default="npc",
        help="数据源名称，对应 processed/{source}_segments.json",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="覆盖默认的 embedding 模型名称",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="覆盖默认的编码批次大小",
    )
    parser.add_argument(
        "--skip-chunk",
        action="store_true",
        help="跳过文本分块，直接对 segments 构建索引（默认会分块）",
    )
    args = parser.parse_args()

    segments_file = PROCESSED_DIR / f"{args.source}_segments.json"
    if not segments_file.exists():
        logger.error(f"分段文件不存在: {segments_file}")
        logger.info("请先运行: python scripts/run_crawler.py --source npc --clean")
        return

    with open(segments_file, "r", encoding="utf-8") as f:
        segments = json.load(f)
    logger.info(f"加载分段数据: {len(segments)} 条，来源: {args.source}")

    # 文本分块
    if args.skip_chunk:
        chunks = segments
        logger.info("跳过文本分块，直接使用 article-level 分段")
    else:
        chunker = LegalChunker()
        chunks = chunker.chunk_segments(segments)
        chunks_file = PROCESSED_DIR / f"{args.source}_chunks.json"
        with open(chunks_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        logger.info(
            f"文本分块完成: {len(segments)} 条分段 -> {len(chunks)} 个 chunk，"
            f"已保存: {chunks_file}"
        )

    model_name = args.model or EMBEDDING_CONFIG["model_name"]
    batch_size = args.batch_size or EMBEDDING_CONFIG.get("batch_size", 32)

    logger.info(f"加载 embedding 模型: {model_name}")
    embedder = EmbeddingModel(
        model_name=model_name,
        device=EMBEDDING_CONFIG["device"],
        normalize_embeddings=EMBEDDING_CONFIG["normalize_embeddings"],
    )
    logger.info(f"模型维度: {embedder.dim}")

    logger.info("开始编码并构建 FAISS 索引...")
    indexer = FaissIndexer(embedder)
    indexer.build(chunks, batch_size=batch_size)

    indexer.save(VECTOR_DIR, index_name=args.source)
    logger.info(f"索引构建完成，共 {indexer.ntotal} 条向量")
    logger.info(f"索引文件: {VECTOR_DIR / args.source}.faiss")
    logger.info(f"元数据文件: {VECTOR_DIR / args.source}_metadata.json")



if __name__ == "__main__":
    main()
