"""
数据清洗与分段模块
- 清理原始文本（去噪、去重、格式统一）
- 按法条/段落分段
- 输出结构化数据供向量化使用
"""
import re
import json
from typing import List, Dict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_DIR, PROCESSED_DIR
from crawler.utils import setup_logger, load_json

logger = setup_logger("cleaner")


class DataCleaner:
    """数据清洗与分段"""

    # 法条正则：第X条
    ARTICLE_PATTERN = re.compile(r"(第[一二三四五六七八九十百千零\d]+条)\s*")
    # 章节正则：第X章/节
    CHAPTER_PATTERN = re.compile(r"(第[一二三四五六七八九十百千零\d]+[章节])\s*")
    # 多余空行
    MULTI_NEWLINE = re.compile(r"\n{3,}")
    # 特殊字符
    SPECIAL_CHARS = re.compile(r"[\u200b\u200c\u200d\ufeff]")

    def clean_text(self, text: str) -> str:
        """基础文本清洗"""
        if not text:
            return ""
        # 去除特殊不可见字符
        text = self.SPECIAL_CHARS.sub("", text)
        # 统一换行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 去除多余空行
        text = self.MULTI_NEWLINE.sub("\n\n", text)
        # 去除行首尾多余空格
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)
        # 去除 HTML 残留标签
        text = re.sub(r"<[^>]+>", "", text)
        # 去除多余空格（保留单个）
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    def split_by_article(self, text: str, title: str = "") -> List[Dict]:
        """
        按法条切分文本
        :return: [{"article_no": "第一条", "content": "...", "title": "..."}]
        """
        segments = []
        # 找到所有 "第X条" 的位置
        matches = list(self.ARTICLE_PATTERN.finditer(text))

        if not matches:
            # 没有法条标记，按段落切分
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for i, para in enumerate(paragraphs):
                segments.append({
                    "title": title,
                    "article_no": f"段落{i+1}",
                    "content": para,
                })
            return segments

        for i, match in enumerate(matches):
            article_no = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            if content:
                segments.append({
                    "title": title,
                    "article_no": article_no,
                    "content": f"{article_no} {content}",
                })

        return segments

    def split_by_chunk(self, text: str, chunk_size: int = 500,
                       overlap: int = 50) -> List[str]:
        """
        按固定长度切分（带重叠），适用于无法条结构的文本
        :param chunk_size: 每段最大字符数
        :param overlap: 重叠字符数
        """
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        return chunks

    def process_single(self, record: Dict) -> List[Dict]:
        """
        处理单条法律记录
        :param record: {"title":..., "content":..., ...}
        :return: 分段后的列表
        """
        title = record.get("title", "")
        content = record.get("content", "")

        # 清理标题中的 HTML 高亮标签
        title = re.sub(r"<[^>]+>", "", title).strip()

        # 清洗
        content = self.clean_text(content)
        if not content or len(content) < 20:
            logger.warning(f"内容过短，跳过: {title}")
            return []

        # 按法条切分
        segments = self.split_by_article(content, title)

        # 补充元数据
        for seg in segments:
            seg["law_type"] = record.get("law_type", "")
            seg["publish_office"] = record.get("publish_office", "")
            seg["publish_date"] = record.get("publish_date", "")
            seg["status"] = record.get("status", "")
            seg["url"] = record.get("url", "")
            seg["source"] = record.get("source", "npc")

        return segments

    def process_file(
        self,
        json_filepath: str,
        law_types: List[str] = None,
    ) -> List[Dict]:
        """
        处理一个 JSON 数据文件
        :param law_types: 法律类型白名单，如 ["宪法", "法律"] 只保留核心法典
        """
        logger.info(f"处理文件: {json_filepath}")
        data = load_json(json_filepath)
        all_segments = []

        for record in data:
            # 类型过滤：如果指定了类型白名单，只保留匹配的记录
            if law_types and record.get("law_type") not in law_types:
                continue
            segments = self.process_single(record)
            all_segments.extend(segments)

        logger.info(f"文件处理完成: {len(data)} 条法律 -> {len(all_segments)} 个分段")
        return all_segments

    def process_all(self, source: str = "npc",
                    law_types: List[str] = None) -> List[Dict]:
        """
        处理指定数据源的所有 JSON 文件
        :param source: "npc" 或 "pkulaw"
        :param law_types: 法律类型白名单，如 ["宪法", "法律"] 只保留核心法典；
                          默认 None = 不过滤
        """
        source_dir = RAW_DIR / source
        if not source_dir.exists():
            logger.error(f"数据目录不存在: {source_dir}")
            return []

        if law_types:
            logger.info(f"法律类型过滤: {law_types}")

        all_segments = []
        json_files = list(source_dir.glob("*.json"))

        for jf in json_files:
            segments = self.process_file(str(jf), law_types=law_types)
            all_segments.extend(segments)


        # 去重（按 title + article_no）
        seen = set()
        unique = []
        for seg in all_segments:
            key = f"{seg['title']}_{seg['article_no']}"
            if key not in seen:
                seen.add(key)
                unique.append(seg)

        # 保存
        output_file = PROCESSED_DIR / f"{source}_segments.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(unique, f, ensure_ascii=False, indent=2)

        logger.info(f"全部清洗完成: {len(unique)} 个分段, 已保存: {output_file}")
        return unique


if __name__ == "__main__":
    cleaner = DataCleaner()
    segments = cleaner.process_all(source="npc")
    print(f"\n清洗完成，共 {len(segments)} 个分段")
    # 打印前3个示例
    for seg in segments[:3]:
        print(f"\n--- {seg['title']} {seg['article_no']} ---")
        print(seg["content"][:100] + "...")
