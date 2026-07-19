"""
项目全局配置文件
"""
import os
from pathlib import Path

# ============ HuggingFace 镜像 / 离线配置 ============
# 国内网络访问 HuggingFace 较慢，默认使用 hf-mirror 镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 离线模式：模型已下载缓存后开启，可避免每次启动联网校验导致卡顿/失败
# 首次使用新机器、或需更新/下载新模型时，改为 False 让其在线下载
USE_HF_OFFLINE = True
if USE_HF_OFFLINE:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# ============ 路径配置 ============

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"           # 原始爬取数据
PROCESSED_DIR = DATA_DIR / "processed"  # 清洗后数据
VECTOR_DIR = DATA_DIR / "vectors"     # 向量索引

for d in [RAW_DIR, PROCESSED_DIR, VECTOR_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============ 爬虫配置 ============
CRAWLER_CONFIG = {
    # 请求间隔（秒），避免被封
    "delay_min": 1.0,
    "delay_max": 3.0,
    # 请求超时
    "timeout": 30,
    # 最大重试次数
    "max_retries": 3,
    # 单次爬取数量上限（0=不限制）
    "max_count": 200,
    # 并发数（国家法律法规数据库API建议串行）
    "concurrency": 1,
}

# ============ 数据源配置 ============
# 主数据源：国家法律法规数据库（官方免费，二期API 2025年8月升级）
NPC_CONFIG = {
    "base_url": "https://flk.npc.gov.cn",
    "api_base": "https://flk.npc.gov.cn/law-search",
    "search_url": "https://flk.npc.gov.cn/law-search/search/list",
    "detail_url": "https://flk.npc.gov.cn/law-search/search/flfgDetails",
    "download_url": "https://flk.npc.gov.cn/law-search/download/mobile",
    # 法律分类 CodeId（根据实际 API 返回校正）
    # 宪法=100, 法律=150, 行政法规=201, 司法解释=311, 地方性法规=230
    "law_types": [
        {"code_id": [], "name": "全部"},
        {"code_id": [100], "name": "宪法"},
        {"code_id": [150], "name": "法律"},
        {"code_id": [201], "name": "行政法规"},
        {"code_id": [311], "name": "司法解释"},
        {"code_id": [230], "name": "地方性法规"},
    ],

}

# 备选数据源：北大法宝（需登录，Selenium 爬取）
PKULAW_CONFIG = {
    "base_url": "https://www.pkulaw.com",
    "search_url": "https://www.pkulaw.com/chl/dc83b04f85042f0dbdfb.html",
    "login_url": "https://www.pkulaw.com/user/login",
    # Selenium 配置
    "headless": True,
    "implicit_wait": 10,
}

# ============ 爬取关键词（核心法典，可按需扩展）============
# 注意：爬虫使用精确标题匹配（search_type=1）+ 法律类型过滤（宪法+法律）
# 关键词应使用法律的官方简称，如"民法典""劳动法"
SEARCH_KEYWORDS = [
    "民法典",
    "刑法",
    "劳动法",
    "劳动合同法",
    "公司法",
    "行政处罚法",
    "行政复议法",
    "行政诉讼法",
    "刑事诉讼法",
    "民事诉讼法",
    "社会保险法",
    "安全生产法",
    "消费者权益保护法",
    "知识产权法",
    "环境保护法",
    "未成年人保护法",
    "个人信息保护法",
    "反垄断法",
    "反不正当竞争法",
    "证券法",
]


# ============ 日志配置 ============
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_LEVEL = "INFO"

# ============ 向量模型配置 ============
# 模型会自动从 HuggingFace 下载，首次使用需要联网
# bge-small-zh-v1.5: 轻量、512维，适合快速验证
# bge-large-zh-v1.5: 1024维，效果更好，适合正式使用
EMBEDDING_CONFIG = {
    "model_name": "BAAI/bge-large-zh-v1.5",
    "device": "cpu",               # 省显存给 LLM，embedding CPU 只慢 0.5s
    "normalize_embeddings": True,
    "batch_size": 10,
}

# ============ FAISS 索引配置 ============
VECTOR_CONFIG = {
    "index_type": "IndexFlatIP",  # 归一化后，内积等价于余弦相似度
    "top_k": 5,                   # 默认检索返回条数
}

