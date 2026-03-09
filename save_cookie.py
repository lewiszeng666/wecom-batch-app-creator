"""
save_cookie.py
企业微信后台登录预存工具

在有显示器的环境执行，扫码登录后保存会话到 browser_data/ 目录。
后续 batch_creator.py 自动复用此会话，无需重复登录。

用法：
    python save_cookie.py
"""

import json
import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

WECOM_LOGIN = "https://work.weixin.qq.com/wework_admin/loginpage_wx"
WECOM_FRAME = "https://work.weixin.qq.com/wework_admin/frame#index"


def load_config(config_path: str = "config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_session(config_path: str = "config.json"):
    config = load_config(config_path)
    browser_data_dir = str(Path(config.get("browser_data_dir", "browser_data")).resolve())
    Path(browser_data_dir).mkdir(parents=True, exist_ok=True)

    logger.info(f"会话数据目录: {browser_data_dir}")
    logger.info("启动浏览器，请扫码登录企业微信后台...")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=browser_data_dir,
            headless=False,  # 必须有头，用于扫码
            args=["--no-sandbox"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(WECOM_LOGIN, wait_until="domcontentloaded")

        logger.info("请在浏览器中扫码登录，等待跳转...")

        # 等待登录成功（URL 变为后台首页）
        for _ in range(120):  # 最多等 2 分钟
            time.sleep(1)
            current_url = page.url
            if "frame" in current_url and "loginpage" not in current_url:
                logger.info(f"登录成功！当前 URL: {current_url}")
                break
        else:
            logger.error("登录超时，请重试")
            browser.close()
            return

        # 等待页面完全加载
        time.sleep(3)
        logger.info("会话已保存到 browser_data/ 目录")
        logger.info("现在可以关闭浏览器，运行 python main.py 开始批量创建应用")

        input("按 Enter 键关闭浏览器...")
        browser.close()


if __name__ == "__main__":
    save_session()
