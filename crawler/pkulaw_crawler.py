"""
北大法宝爬虫（备选数据源）
网站: https://www.pkulaw.com/

注意:
1. 北大法宝部分内容需登录/付费，本爬虫使用 Selenium 模拟浏览器
2. 需要安装 Chrome 浏览器和对应驱动
3. 建议先用国家法律法规数据库(npc_crawler)获取主要数据

使用前安装:
    pip install selenium webdriver-manager
"""
import time
import re
import json
from typing import List, Dict, Optional
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import PKULAW_CONFIG, CRAWLER_CONFIG
from crawler.utils import setup_logger, save_json, random_delay

logger = setup_logger("pkulaw_crawler")


class PKULawCrawler:
    """北大法宝爬虫（Selenium 实现）"""

    def __init__(self, headless: bool = None):
        self.base_url = PKULAW_CONFIG["base_url"]
        self.search_url = PKULAW_CONFIG["search_url"]
        self.headless = headless if headless is not None else PKULAW_CONFIG["headless"]
        self.driver = None

    def _init_driver(self):
        """初始化 Selenium WebDriver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            logger.error("请先安装: pip install selenium webdriver-manager")
            raise

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # 禁用自动化检测
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.implicitly_wait(PKULAW_CONFIG["implicit_wait"])

        # 隐藏 webdriver 特征
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        logger.info("Selenium WebDriver 初始化完成")

    def login(self, username: str = "", password: str = "") -> bool:
        """
        登录北大法宝（如有账号）
        :return: 是否登录成功
        """
        if not username or not password:
            logger.warning("未提供账号密码，将以游客身份访问（可能无法查看全文）")
            return False

        try:
            self.driver.get(PKULAW_CONFIG["login_url"])
            time.sleep(2)

            # 定位登录表单（实际选择器需根据页面调整）
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            user_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            user_input.send_keys(username)
            self.driver.find_element(By.NAME, "password").send_keys(password)
            self.driver.find_element(By.CSS_SELECTOR, "button[type=submit]").click()
            time.sleep(3)

            if "login" not in self.driver.current_url.lower():
                logger.info("登录成功")
                return True
            else:
                logger.error("登录失败")
                return False
        except Exception as e:
            logger.error(f"登录异常: {e}")
            return False

    def search(self, keyword: str) -> List[Dict]:
        """
        搜索法律法规
        :param keyword: 搜索关键词
        :return: 搜索结果列表
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        results = []
        try:
            self.driver.get(self.search_url)
            time.sleep(2)

            # 搜索框（实际选择器需根据页面调整）
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='搜索']"))
            )
            search_box.clear()
            search_box.send_keys(keyword)

            # 点击搜索
            search_btn = self.driver.find_element(By.CSS_SELECTOR, "button.search-btn")
            search_btn.click()
            time.sleep(3)

            # 解析搜索结果列表
            items = self.driver.find_elements(By.CSS_SELECTOR, ".search-result-item")
            for item in items[:CRAWLER_CONFIG["max_count"]]:
                try:
                    title_el = item.find_element(By.CSS_SELECTOR, ".title a")
                    title = title_el.text
                    link = title_el.get_attribute("href")
                    summary = item.find_element(By.CSS_SELECTOR, ".summary").text

                    results.append({
                        "title": title,
                        "url": link,
                        "summary": summary,
                    })
                    logger.info(f"  找到: {title}")
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"搜索 '{keyword}' 失败: {e}")

        return results

    def get_detail(self, url: str) -> Optional[Dict]:
        """
        获取法律详情页内容
        """
        from selenium.webdriver.common.by import By

        try:
            self.driver.get(url)
            time.sleep(2)

            # 详情内容（实际选择器需根据页面调整）
            content_el = self.driver.find_element(By.CSS_SELECTOR, ".law-content, .article-content, .content")
            content = content_el.text

            title = self.driver.find_element(By.CSS_SELECTOR, "h1, .title").text

            return {
                "title": title.strip(),
                "url": url,
                "content": content.strip(),
            }
        except Exception as e:
            logger.error(f"获取详情失败: {url}, {e}")
            return None

    def crawl(self, keywords: List[str], max_per_keyword: int = 10) -> List[Dict]:
        """
        主爬取方法
        :param keywords: 关键词列表
        :param max_per_keyword: 每个关键词最大数量
        """
        self._init_driver()

        all_results = []
        try:
            for kw in keywords:
                logger.info(f"=== 搜索关键词: '{kw}' ===")
                search_results = self.search(kw)

                for i, item in enumerate(search_results[:max_per_keyword]):
                    random_delay(2, 4)  # Selenium 爬取延时更长
                    detail = self.get_detail(item["url"])
                    if detail and detail["content"]:
                        all_results.append(detail)
                        logger.info(f"  [{i+1}] {detail['title']}")

        finally:
            self.close()

        logger.info(f"北大法宝爬取完成, 共 {len(all_results)} 条")
        return all_results

    def save_results(self, results: List[Dict], filename: str = None):
        if filename is None:
            filename = f"pkulaw_laws_{int(time.time())}.json"
        filepath = save_json(results, filename, subdir="pkulaw")
        logger.info(f"已保存: {filepath}")

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("WebDriver 已关闭")


if __name__ == "__main__":
    # 注意: 使用前需修改 login() 中的账号密码，或以游客模式访问
    crawler = PKULawCrawler(headless=False)  # 调试时设为 False 可见浏览器
    results = crawler.crawl(
        keywords=["劳动法", "民法典"],
        max_per_keyword=5,
    )
    crawler.save_results(results)
