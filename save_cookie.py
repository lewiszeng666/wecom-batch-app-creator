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


def load_config(config_path: str = "config.json") -> dict:
    if not Path(config_path).exists():
        # 使用默认配置
        return {"browser_data_dir": "browser_data"}
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
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(WECOM_LOGIN, wait_until="domcontentloaded")

        print("\n" + "═" * 60)
        print("  操作步骤：")
        print("  1. 在弹出的浏览器窗口中，用企业微信 App 扫码")
        print("  2. 手机上点击「确认登录」")
        print("  3. 等待浏览器跳转到企业微信后台首页")
        print("  4. 确认已进入后台后，回到此终端按 Enter 保存会话")
        print("═" * 60 + "\n")

        # 同时在后台轮询 URL，如果自动跳转了就提示用户
        import threading

        def watch_url():
            for _ in range(120):
                time.sleep(1)
                try:
                    current_url = page.url
                    if "frame" in current_url and "loginpage" not in current_url:
                        print(f"\n✅ 检测到登录成功！当前 URL: {current_url}")
                        print("   请按 Enter 保存会话并关闭浏览器\n")
                        return
                except Exception:
                    pass

        watcher = threading.Thread(target=watch_url, daemon=True)
        watcher.start()

        input("登录完成后按 Enter 键保存会话并关闭浏览器...")

        # 验证登录状态
        try:
            current_url = page.url
            if "loginpage" in current_url or "login" in current_url.lower():
                logger.warning("⚠️  检测到当前仍在登录页，会话可能未保存成功")
                logger.warning("   请确认已在企业微信 App 上点击「确认登录」后再保存")
            else:
                logger.info(f"✅ 登录状态确认，当前 URL: {current_url}")
                logger.info("✅ 会话已保存到 browser_data/ 目录")
                logger.info("   现在可以运行 python main.py 开始批量创建应用")
        except Exception:
            logger.info("会话已保存（无法验证 URL）")

        browser.close()


if __name__ == "__main__":
    save_session()
