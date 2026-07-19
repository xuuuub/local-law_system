"""
爬虫运行入口脚本
用法:
    python scripts/run_crawler.py --source npc --keywords 劳动法 民法典
    python scripts/run_crawler.py --source npc --type all
    python scripts/run_crawler.py --source pkulaw --keywords 劳动法
    python scripts/run_crawler.py --clean npc
"""
import argparse
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SEARCH_KEYWORDS, CRAWLER_CONFIG
from crawler.utils import setup_logger

logger = setup_logger("run_crawler")


def run_npc(keywords=None, law_type="all", max_count=20, clean=False):
    """运行国家法律法规数据库爬虫"""
    from crawler.npc_crawler import NPCCrawler

    crawler = NPCCrawler()

    if law_type != "all" and not keywords:
        # 按类型爬取
        type_map = {"law": "flfg", "admin": "adminreg", "judicial": "sfjs"}
        lt = type_map.get(law_type, "")
        results = crawler.crawl_by_type(law_type=lt, type_name=law_type,
                                        max_count=max_count)
    else:
        # 按关键词爬取
        kws = keywords if keywords else SEARCH_KEYWORDS

        # 如果指定了 --type law，客户端用 flxz 过滤，只保留"宪法 + 法律"
        # 使用 flxz（类型名）比 code_id 更可靠（法律下有多个 code：120~170）
        flxz_filter = ["宪法", "法律"] if law_type == "law" else None

        results = crawler.run(
            keywords=kws,
            max_per_keyword=max_count,
            flxz_filter=flxz_filter,
        )

    crawler.save_results(results)

    if clean:
        run_clean("npc")

    return results


def run_pkulaw(keywords=None, max_count=5):
    """运行北大法宝爬虫"""
    from crawler.pkulaw_crawler import PKULawCrawler

    crawler = PKULawCrawler(headless=False)
    kws = keywords if keywords else SEARCH_KEYWORDS[:3]
    results = crawler.crawl(keywords=kws, max_per_keyword=max_count)
    crawler.save_results(results)
    return results


def run_clean(source="npc", law_types=None):
    """运行数据清洗
    :param law_types: 法律类型白名单，默认 ["宪法", "法律"] 只保留核心法典
    """
    from crawler.cleaner import DataCleaner

    if law_types is None:
        law_types = ["宪法", "法律"]  # 默认只保留核心法典

    cleaner = DataCleaner()
    segments = cleaner.process_all(source=source, law_types=law_types)
    return segments


def main():
    parser = argparse.ArgumentParser(description="法律法规爬虫工具")
    parser.add_argument("--source", choices=["npc", "pkulaw"],
                        default="npc", help="数据源")
    parser.add_argument("--keywords", nargs="*", default=None,
                        help="搜索关键词列表")
    parser.add_argument("--type", choices=["all", "law", "admin", "judicial"],
                        default="all",
                        help="法律类型(仅npc)：law=宪法+法律, admin=行政法规, judicial=司法解释")
    parser.add_argument("--max", type=int, default=20,
                        help="每个关键词/类型最大爬取数")
    parser.add_argument("--clean", action="store_true",
                        help="爬取后自动清洗数据")
    parser.add_argument("--clean-only", action="store_true",
                        help="仅执行清洗")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("法律法规爬虫启动")
    logger.info(f"数据源: {args.source}")
    logger.info("=" * 60)

    if args.clean_only:
        run_clean(args.source)
        return

    if args.source == "npc":
        run_npc(keywords=args.keywords, law_type=args.type,
                max_count=args.max, clean=args.clean)
    elif args.source == "pkulaw":
        run_pkulaw(keywords=args.keywords, max_count=args.max)

    logger.info("全部任务完成!")


if __name__ == "__main__":
    main()
