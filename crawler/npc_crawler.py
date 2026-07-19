"""
国家法律法规数据库爬虫（主数据源）- 二期 API
网站: https://flk.npc.gov.cn/
官方免费，无需登录

API 流程（2025年8月二期升级后）:
1. 搜索: POST /law-search/search/list  (JSON body)
   返回 rows[].bbbs（法规唯一ID）
2. 详情: GET /law-search/search/flfgDetails?bbbs=xxx
   返回法规元数据 + 文件路径
3. 下载: GET /law-search/download/mobile?format=docx&bbbs=xxx
   移动端接口，直接返回 DOCX 二进制流
4. 用 python-docx 解析正文

注意事项:
- 请求间隔建议 0.5s，连续约 20 次后可能限流
- pageSize 建议 100 减少请求次数
- Windows 下 JSON body 中文会被 Unicode 转义（正常）
"""
import requests
import json
import re
import time
import io
from typing import List, Dict, Optional
from pathlib import Path
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import NPC_CONFIG, CRAWLER_CONFIG, RAW_DIR
from crawler.utils import setup_logger, save_json

logger = setup_logger("npc_crawler")

# 二期 API 通用请求头
API_HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://flk.npc.gov.cn/",
}

# 时效性：1=已废止, 2=已修改, 3=现行有效, 4=尚未生效
SXX_MAP = {1: "已废止", 2: "已修改", 3: "现行有效", 4: "尚未生效"}


class NPCCrawler:
    """国家法律法规数据库爬虫（二期 API）"""

    def __init__(self):
        self.base_url = NPC_CONFIG["base_url"]
        self.search_url = NPC_CONFIG["search_url"]
        self.detail_url = NPC_CONFIG["detail_url"]
        self.download_url = NPC_CONFIG["download_url"]
        self.session = requests.Session()
        self.session.headers.update(API_HEADERS)
        self.session.verify = False
        self._docx_parser = None
        self._request_count = 0
        self.collected = []

    def _get_docx_parser(self):
        """延迟导入 python-docx"""
        if self._docx_parser is None:
            try:
                from docx import Document
                self._docx_parser = Document
            except ImportError:
                logger.error("请安装 python-docx: pip install python-docx")
                raise
        return self._docx_parser

    def _smart_delay(self):
        """智能延时：每 15 次请求后长延时避免限流"""
        self._request_count += 1
        if self._request_count % 15 == 0:
            logger.info("已请求 15 次，长延时 3s 避免限流...")
            time.sleep(3)
        else:
            time.sleep(0.5)

    def search_laws(
        self,
        keyword: str = "",
        flfg_code_ids: List[int] = None,
        sxx: List[int] = None,
        page_num: int = 1,
        page_size: int = 100,
        search_type: int = 2,
    ) -> Dict:
        """
        搜索法律法规（POST /law-search/search/list）
        :param keyword: 搜索关键词
        :param flfg_code_ids: 法律分类 CodeId 列表（注意：与关键词一起用会失效）
        :param sxx: 时效性列表 [3]=现行有效
        :param page_num: 页码
        :param page_size: 每页数量（建议 100）
        :param search_type: 1=精确匹配, 2=模糊匹配
        :return: {"code":200, "total":N, "rows":[{"bbbs":..., "title":...}]}
        """
        if sxx is None:
            sxx = [3]  # 默认只搜现行有效
        if flfg_code_ids is None:
            flfg_code_ids = []

        payload = {
            "searchRange": 1,          # 1=标题搜索
            "searchContent": keyword,
            "searchType": search_type,
            "sxx": sxx,
            "sxrq": [],
            "gbrq": [],
            "gbrqYear": [],
            "flfgCodeId": flfg_code_ids,
            "zdjgCodeId": [],
            "xgzlSearch": False,
            "pageNum": page_num,
            "pageSize": page_size,
        }

        for attempt in range(CRAWLER_CONFIG["max_retries"]):
            try:
                self._smart_delay()
                resp = self.session.post(
                    self.search_url, json=payload,
                    timeout=CRAWLER_CONFIG["timeout"], verify=False,
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("code") != 200:
                    logger.warning(f"搜索返回非200: {data.get('msg')}")
                    return {}

                total = data.get("total", 0)
                rows = data.get("rows", [])
                logger.info(f"搜索成功: 关键词='{keyword}', "
                          f"第{page_num}页, 返回{len(rows)}条(共{total}条)")
                return data

            except (requests.RequestException, json.JSONDecodeError) as e:
                wait = 2 ** (attempt + 1)
                logger.warning(f"搜索失败(第{attempt+1}次): {e}, {wait}s后重试")
                time.sleep(wait)

        logger.error(f"搜索彻底失败: 关键词='{keyword}'")
        return {}

    def get_detail(self, bbbs: str) -> Optional[Dict]:
        """
        获取法规详情（GET /law-search/search/flfgDetails?bbbs=xxx）
        :return: 法规元数据 + 文件路径 + 结构树
        """
        for attempt in range(CRAWLER_CONFIG["max_retries"]):
            try:
                self._smart_delay()
                resp = self.session.get(
                    self.detail_url,
                    params={"bbbs": bbbs},
                    timeout=CRAWLER_CONFIG["timeout"], verify=False,
                )
                resp.raise_for_status()
                data = resp.json()
                logger.debug(f"获取详情成功: {data.get('title')}")
                return data
            except (requests.RequestException, json.JSONDecodeError) as e:
                wait = 2 ** (attempt + 1)
                logger.warning(f"获取详情失败(第{attempt+1}次): {e}, {wait}s后重试")
                time.sleep(wait)
        return None

    def download_docx(self, bbbs: str) -> Optional[bytes]:
        """
        下载 DOCX 文件（移动端接口，直接返回二进制流）
        GET /law-search/download/mobile?format=docx&bbbs=xxx&fileId=
        :return: DOCX 文件二进制内容，失败返回 None
        """
        for attempt in range(CRAWLER_CONFIG["max_retries"]):
            try:
                self._smart_delay()
                resp = self.session.get(
                    self.download_url,
                    params={"format": "docx", "bbbs": bbbs, "fileId": ""},
                    timeout=60, verify=False,
                )
                resp.raise_for_status()

                # 检查是否返回了 JSON 错误（而非二进制文件）
                content_type = resp.headers.get("Content-Type", "")
                if "json" in content_type:
                    data = resp.json()
                    logger.warning(f"下载返回JSON: {data.get('msg', data)}")
                    return None

                content = resp.content
                if len(content) < 100:
                    logger.warning(f"下载内容过短: {len(content)} bytes")
                    return None

                logger.debug(f"DOCX 下载成功: bbbs={bbbs}, {len(content)} bytes")
                return content

            except requests.RequestException as e:
                wait = 2 ** (attempt + 1)
                logger.warning(f"下载失败(第{attempt+1}次): {e}, {wait}s后重试")
                time.sleep(wait)
        return None

    def parse_docx(self, docx_bytes: bytes) -> str:
        """用 python-docx 解析 DOCX 二进制内容为纯文本"""
        try:
            Document = self._get_docx_parser()
            doc = Document(io.BytesIO(docx_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
            return text
        except Exception as e:
            logger.error(f"DOCX 解析失败: {e}")
            return ""

    def build_record(self, row: Dict, detail: Dict, content: str) -> Dict:
        """
        组装最终记录
        :param row: 搜索结果中的一行
        :param detail: 详情数据
        :param content: 正文文本
        """
        sxx_val = detail.get("sxx", row.get("sxx", ""))
        if isinstance(sxx_val, str):
            sxx_int = int(sxx_val) if sxx_val.isdigit() else 0
        else:
            sxx_int = sxx_val

        # 清理标题中的 HTML 高亮标签
        title_raw = detail.get("title", row.get("title", ""))
        title = re.sub(r"<[^>]+>", "", title_raw).strip()

        return {
            "title": title,
            "law_type": detail.get("flxz", row.get("flxz", "")),
            "publish_office": detail.get("zdjgName", row.get("zdjgName", "")),
            "publish_date": detail.get("gbrq", row.get("gbrq", "")),
            "effective_date": detail.get("sxrq", row.get("sxrq", "")),
            "status": SXX_MAP.get(sxx_int, str(sxx_val)),
            "bbbs": detail.get("bbbs", row.get("bbbs", "")),
            "url": f"{self.base_url}/detail2.html?{detail.get('bbbs', row.get('bbbs', ''))}",
            "content": content.strip(),
            "source": "npc",
        }

    def crawl_by_keyword(
        self,
        keyword: str,
        max_count: int = 50,
        flxz_filter: List[str] = None,
        search_type: int = 1,
    ) -> List[Dict]:
        """按关键词爬取法律法规
        :param flxz_filter: 按法律类型名称过滤（推荐），如 ["宪法", "法律"]
                            法律在不同子类下有不同 code_id（120~170），
                            用 flxz 过滤比 code_id 更可靠
        :param search_type: 1=精确匹配, 2=模糊匹配
        """
        logger.info(f"=== 开始爬取关键词: '{keyword}' ===")
        if flxz_filter:
            logger.info(f"客户端类型过滤: {flxz_filter}")
        logger.info(f"搜索类型: {'精确匹配' if search_type == 1 else '模糊匹配'}")
        results = []
        page_num = 1
        page_size = 100

        while len(results) < max_count:
            # 不传 code_id 给 API（会干扰关键词搜索），改为客户端过滤
            data = self.search_laws(
                keyword=keyword,
                page_num=page_num,
                page_size=page_size,
                search_type=search_type,
            )
            if not data:
                break

            rows = data.get("rows", [])
            total = data.get("total", 0)
            if not rows:
                logger.info(f"关键词 '{keyword}' 无更多数据")
                break

            for row in rows:
                if len(results) >= max_count:
                    break

                # 客户端过滤：按法律类型名称（flxz）过滤
                if flxz_filter:
                    row_flxz = row.get("flxz", "")
                    if row_flxz not in flxz_filter:
                        continue

                bbbs = row.get("bbbs", "")
                if not bbbs:
                    continue

                # 获取详情
                detail = self.get_detail(bbbs)
                if not detail:
                    continue

                # 下载并解析 DOCX
                docx_bytes = self.download_docx(bbbs)
                if not docx_bytes:
                    logger.warning(f"  下载失败，跳过: {row.get('title')}")
                    continue

                content = self.parse_docx(docx_bytes)
                if not content or len(content) < 20:
                    logger.warning(f"  内容为空，跳过: {row.get('title')}")
                    continue

                record = self.build_record(row, detail, content)
                results.append(record)
                logger.info(f"  [{len(results)}] {record['title']} "
                          f"({len(content)} 字符)")

            # 判断是否还有下一页
            if page_num * page_size >= total:
                break
            page_num += 1
            if page_num > 20:
                break

        logger.info(f"关键词 '{keyword}' 爬取完成, 共 {len(results)} 条")
        return results

    def crawl_by_type(self, flfg_code_ids: List[int], type_name: str = "全部",
                      max_count: int = 100) -> List[Dict]:
        """按法律类型爬取（通过 flfgCodeId 过滤，关键词为空）"""
        logger.info(f"=== 开始爬取类型: '{type_name}' ===")
        results = []
        page_num = 1
        page_size = 100

        while len(results) < max_count:
            data = self.search_laws(
                keyword="", flfg_code_ids=flfg_code_ids,
                page_num=page_num, page_size=page_size,
            )
            if not data:
                break

            rows = data.get("rows", [])
            total = data.get("total", 0)
            if not rows:
                break

            for row in rows:
                if len(results) >= max_count:
                    break
                bbbs = row.get("bbbs", "")
                if not bbbs:
                    continue

                detail = self.get_detail(bbbs)
                if not detail:
                    continue

                docx_bytes = self.download_docx(bbbs)
                if not docx_bytes:
                    continue

                content = self.parse_docx(docx_bytes)
                if not content or len(content) < 20:
                    continue

                record = self.build_record(row, detail, content)
                results.append(record)
                logger.info(f"  [{len(results)}] {record['title']}")

            if page_num * page_size >= total:
                break
            page_num += 1
            if page_num > 30:
                break

        logger.info(f"类型 '{type_name}' 爬取完成, 共 {len(results)} 条")
        return results

    def run(
        self,
        keywords: List[str] = None,
        max_per_keyword: int = 20,
        flxz_filter: List[str] = None,
        search_type: int = 1,
    ) -> List[Dict]:
        """主运行方法
        :param flxz_filter: 按关键词爬取时的类型过滤，如 ["宪法", "法律"]
        :param search_type: 1=精确匹配, 2=模糊匹配
        """
        all_results = []

        if keywords:
            for kw in keywords:
                results = self.crawl_by_keyword(
                    kw,
                    max_count=max_per_keyword,
                    flxz_filter=flxz_filter,
                    search_type=search_type,
                )
                all_results.extend(results)
        else:
            for lt in NPC_CONFIG["law_types"]:
                results = self.crawl_by_type(
                    flfg_code_ids=lt["code_id"], type_name=lt["name"],
                    max_count=CRAWLER_CONFIG["max_count"],
                )
                all_results.extend(results)

        # 去重
        seen = set()
        unique = []
        for r in all_results:
            if r["title"] not in seen:
                seen.add(r["title"])
                unique.append(r)

        self.collected = unique
        logger.info(f"全部爬取完成，去重后共 {len(unique)} 条")
        return unique

    def save_results(self, results: List[Dict], filename: str = None):
        """保存结果到 JSON 和 TXT"""
        if filename is None:
            filename = f"npc_laws_{int(time.time())}.json"
        filepath = save_json(results, filename, subdir="npc")
        logger.info(f"JSON 已保存: {filepath}")

        # 同时保存为单条 txt
        txt_dir = RAW_DIR / "npc" / "txt"
        txt_dir.mkdir(parents=True, exist_ok=True)
        for item in results:
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", item["title"])[:50]
            txt_path = txt_dir / f"{safe_title}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"标题: {item['title']}\n")
                f.write(f"类型: {item['law_type']}\n")
                f.write(f"发布机关: {item['publish_office']}\n")
                f.write(f"发布日期: {item['publish_date']}\n")
                f.write(f"生效日期: {item['effective_date']}\n")
                f.write(f"状态: {item['status']}\n")
                f.write(f"来源: {item['url']}\n")
                f.write("=" * 60 + "\n")
                f.write(item["content"])
        logger.info(f"TXT 文件已保存: {txt_dir} ({len(results)} 个文件)")


if __name__ == "__main__":
    crawler = NPCCrawler()
    results = crawler.run(
        keywords=["劳动法", "劳动合同法", "民法典"],
        max_per_keyword=10,
    )
    crawler.save_results(results)
