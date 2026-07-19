"""
爬虫工具模块
- 随机 User-Agent
- 请求延时
- 日志配置
- 文件保存
"""
import random
import time
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import LOG_DIR, LOG_LEVEL, RAW_DIR


# ============ User-Agent 池 ============
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_random_ua():
    """返回随机 User-Agent"""
    return random.choice(USER_AGENTS)


def get_headers():
    """返回带随机 UA 的请求头"""
    return {
        "User-Agent": get_random_ua(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def random_delay(min_sec=1.0, max_sec=3.0):
    """随机延时，防止请求过快"""
    time.sleep(random.uniform(min_sec, max_sec))


# ============ 日志配置 ============
def setup_logger(name="crawler", log_file=None):
    """配置并返回 logger"""
    if log_file is None:
        log_file = LOG_DIR / f"crawler_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL))

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # 文件输出
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger


# ============ 文件保存 ============
def save_json(data, filename, subdir=None):
    """保存数据为 JSON 文件"""
    save_dir = RAW_DIR if subdir is None else RAW_DIR / subdir
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def save_txt(text, filename, subdir=None):
    """保存文本为 txt 文件"""
    save_dir = RAW_DIR if subdir is None else RAW_DIR / subdir
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    return filepath


def load_json(filepath):
    """加载 JSON 文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
