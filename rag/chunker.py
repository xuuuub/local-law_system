"""
法律文本分块模块（v2）

分块原则：
原则一：长法条 → 切块但不丢魂
  - 单条 > 500 字符：按逻辑边界（项/句/款）拆分为子块
  - 每个子块必须独立保留"第X条"标题作为前缀
  - 元数据：chunk_total、chunk_index、parent_article_id

原则二：短法条 → 扩写但不篡改
  - 单条 < 150 字符：向量化时拼接"《法律名》第X条：正文"作为 embedding_text
  - 原内容 content 不修改，展示时保持纯净
  - embedding_text 只用于向量编码，提升短条款召回率
"""
import re
import json
from pathlib import Path
from typing import List, Dict


class LegalChunker:
    """法律文本分块器 v2"""

    # "项" 正则：匹配 （一）、（二） 或 (一)(二) 或 1、2、 等
    XIANG_PATTERN = re.compile(
        r"(?:"
        r"（[一二三四五六七八九十百千零]+）"   # 中文括号项
        r"|\([一二三四五六七八九十百千零]+\)" # 英文括号项
        r")"
    )
    # 句子结尾：。；
    SENTENCE_END = re.compile(r"([。；])")

    def __init__(
        self,
        long_threshold: int = 500,
        short_threshold: int = 150,
        max_chunk_size: int = 600,
        min_chunk_size: int = 80,
    ):
        self.long_threshold = long_threshold
        self.short_threshold = short_threshold
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size

    def _article_prefix(self, segment: Dict) -> str:
        """生成法条前缀，例如 '《劳动法》第二十一条'"""
        title = segment.get("title", "")
        article_no = segment.get("article_no", "")
        return f"《{title}》{article_no}"

    def _parent_article_id(self, segment: Dict) -> str:
        title = segment.get("title", "")
        article_no = segment.get("article_no", "")
        return f"{title}__{article_no}"

    def _split_by_xiang(self, text: str) -> List[str]:
        """按'项'拆分文本"""
        matches = list(self.XIANG_PATTERN.finditer(text))
        if len(matches) < 2:
            return []

        parts = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            part = text[start:end].strip()
            if part:
                parts.append(part)
        return parts

    def _split_by_sentences(self, text: str) -> List[str]:
        """按句子/段落拆分"""
        raw_sentences = []
        start = 0
        for match in self.SENTENCE_END.finditer(text):
            end = match.end()
            sentence = text[start:end].strip()
            if sentence:
                raw_sentences.append(sentence)
            start = end
        tail = text[start:].strip()
        if tail:
            raw_sentences.append(tail)
        if not raw_sentences:
            return [text]

        chunks = []
        current = raw_sentences[0]
        for sentence in raw_sentences[1:]:
            if len(current) + len(sentence) <= self.max_chunk_size:
                current += sentence
            else:
                if len(current) >= self.min_chunk_size or not chunks:
                    chunks.append(current)
                else:
                    chunks[-1] += current
                current = sentence
        if current:
            if len(current) >= self.min_chunk_size or not chunks:
                chunks.append(current)
            else:
                chunks[-1] += current
        return chunks if chunks else [text]

    def _merge_tiny_chunks(self, parts: List[str]) -> List[str]:
        if not parts:
            return parts
        merged = [parts[0]]
        for part in parts[1:]:
            if len(merged[-1]) < self.min_chunk_size:
                merged[-1] += " " + part
            elif len(part) < self.min_chunk_size:
                merged[-1] += " " + part
            else:
                merged.append(part)
        return merged

    def _build_embedding_text(self, segment: Dict, content: str) -> str:
        """
        原则二：短法条扩写向量文本
        - content 本身不变，只拼接法条上下文用于向量编码
        """
        prefix = self._article_prefix(segment)
        return f"{prefix}：{content}"

    def chunk_article(self, segment: Dict) -> List[Dict]:
        """
        对单条法条进行分块
        """
        content = segment.get("content", "").strip()
        if not content:
            return []

        title = segment.get("title", "")
        article_no = segment.get("article_no", "")
        parent_id = self._parent_article_id(segment)
        article_content_len = len(content)

        # 分离出法条正文（去掉开头的"第X条 "前缀，后面加上时会统一处理）
        article_prefix = self._article_prefix(segment)

        # 短法条：不切，但向量化时要扩写（原则二）
        if article_content_len < self.short_threshold:
            chunk = self._make_chunk(
                segment, content, article_prefix,
                chunk_index=0, chunk_total=1, parent_id=parent_id,
            )
            return [chunk]

        # 中等长度法条：不切
        if article_content_len <= self.long_threshold:
            chunk = self._make_chunk(
                segment, content, article_prefix,
                chunk_index=0, chunk_total=1, parent_id=parent_id,
            )
            return [chunk]

        # 长法条：按逻辑边界拆分（原则一）
        xiang_parts = self._split_by_xiang(content)
        if xiang_parts:
            final_parts = []
            for part in xiang_parts:
                if len(part) > self.max_chunk_size:
                    final_parts.extend(self._split_by_sentences(part))
                else:
                    final_parts.append(part)
        else:
            final_parts = self._split_by_sentences(content)

        final_parts = self._merge_tiny_chunks(final_parts)

        chunks = []
        for idx, part in enumerate(final_parts):
            # 原则一：每个子块必须独立保留"第X条"作为前缀
            chunk = self._make_chunk(
                segment, part, article_prefix,
                chunk_index=idx, chunk_total=len(final_parts),
                parent_id=parent_id,
            )
            chunks.append(chunk)
        return chunks

    def _make_chunk(
        self,
        segment: Dict,
        content: str,
        article_prefix: str,
        chunk_index: int,
        chunk_total: int,
        parent_id: str,
    ) -> Dict:
        """构造 chunk 字典"""
        is_split = chunk_total > 1
        is_short = len(content) < self.short_threshold and chunk_total == 1

        # content: 原有内容不变
        display_content = content

        # embedding_text: 向量化时使用的文本（原则一：加前缀 / 原则二：扩写）
        if is_short:
            # 原则二：短法条扩写
            embedding_content = self._build_embedding_text(segment, content)
        elif is_split:
            # 原则一：拆分后每个子块带上法条前缀
            embedding_content = f"{article_prefix}：{content}"
        else:
            embedding_content = content

        return {
            "title": segment.get("title", ""),
            "article_no": segment.get("article_no", ""),
            "parent_article_id": parent_id,
            "content": display_content,
            "embedding_text": embedding_content,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "chunk_type": "split" if is_split else ("short" if is_short else "whole"),
            "law_type": segment.get("law_type", ""),
            "publish_office": segment.get("publish_office", ""),
            "publish_date": segment.get("publish_date", ""),
            "status": segment.get("status", ""),
            "url": segment.get("url", ""),
            "source": segment.get("source", "npc"),
        }

    def chunk_segments(self, segments: List[Dict]) -> List[Dict]:
        chunks = []
        for segment in segments:
            chunks.extend(self.chunk_article(segment))
        return chunks

    def process_file(
        self, input_file: Path, output_file: Path
    ) -> List[Dict]:
        with open(input_file, "r", encoding="utf-8") as f:
            segments = json.load(f)
        chunks = self.chunk_segments(segments)
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        return chunks


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import PROCESSED_DIR

    chunker = LegalChunker()
    chunks = chunker.process_file(
        PROCESSED_DIR / "npc_segments.json",
        PROCESSED_DIR / "npc_chunks.json",
    )
    print(f"分块完成：{len(chunks)} 个 chunk")

    lengths = [len(c["content"]) for c in chunks]
    print(f"最短: {min(lengths)} 字, 最长: {max(lengths)} 字, 平均: {sum(lengths)/len(lengths):.1f} 字")

    # 统计
    split_count = sum(1 for c in chunks if c["chunk_type"] == "split")
    short_count = sum(1 for c in chunks if c["chunk_type"] == "short")
    whole_count = sum(1 for c in chunks if c["chunk_type"] == "whole")
    print(f"whole: {whole_count}, split: {split_count}, short: {short_count}")

    print("\n拆分示例：")
    for c in chunks:
        if c["chunk_type"] == "split":
            et = c["embedding_text"]
            print(f"  {c['title']} {c['article_no']} [{c['chunk_index']+1}/{c['chunk_total']}]")
            print(f"  embedding: {et[:100]}...")
            break

    print("\n短法条扩写示例：")
    for c in chunks:
        if c["chunk_type"] == "short":
            print(f"  content: {c['content']}")
            print(f"  embedding_text: {c['embedding_text']}")
            break
