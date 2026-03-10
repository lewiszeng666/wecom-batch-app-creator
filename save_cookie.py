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
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

WECOM_LOGIN = "https://work.weixin.qq.com/wework_admin/loginpage_wx"


def load_config(config_path: str = "config.json") -> dict:
    if not Path(config_path).exists():
        return {"browser_data_dir": "browser_data"}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_logged_in(page) -> bool:
    """
    判断是否已登录企微后台。
    策略（满足任意一条即认为已登录）：
      1. URL 不含 loginpage_wx（已跳转到后台或中间页）
      2. 页面 DOM 中存在企微后台导航元素（如 .ww_nav、#js_main 等）
    """
    try:
        url = page.url
        # 策略 1：URL 已离开登录页
        if "loginpage_wx" not in url and "work.weixin.qq.com" in url:
            return True
        # 策略 2：DOM 中检测到后台内容
        has_backend = page.evaluate("""
            () => {
                // 企微后台特有的导航或主容器
                var selectors = [
                    '#js_main', '.ww_nav', '.js_leftNav',
                    '#js_sidebar', '.frame_nav', '[class*="leftNav"]',
                    '.js_indexPage', '#js_frame'
                ];
                for (var s of selectors) {
                    if (document.querySelector(s)) return true;
                }
                // 检查 title 是否变为后台标题
                var title = document.title;
                if (title && title !== '企业微信' && title !== 'WeCom' && title.length > 2) {
                    // 登录页 title 通常就是"企业微信"或"WeCom"
                    return !document.querySelector('input[placeholder*="手机"]') &&
                           !document.querySelector('.login_container') &&
                           !document.querySelector('#loginForm');
                }
                return false;
            }
        """)
        return bool(has_backend)
    except Exception:
        return False


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
                "--window-size=1280,800",
            ],
            ignore_default_args=["--enable-automation"],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(WECOM_LOGIN, wait_until="domcontentloaded")

        print("\n" + "═" * 60)
        print("  操作步骤：")
        print("  1. 在弹出的浏览器窗口中，用企业微信 App 扫码")
        print("  2. 手机上点击「确认登录」")
        print("  3. 如有多企业选择页，选择对应企业")
        print("  4. 等待浏览器跳转到企业微信后台（看到应用列表等内容）")
        print("  5. 确认已进入后台后，回到此终端按 Enter 保存会话")
        print("═" * 60 + "\n")

        # 后台监听：自动检测跳转并提示
        detected = threading.Event()

        def watch_url():
            for _ in range(180):  # 最多等 3 分钟
                time.sleep(1)
                try:
                    if _is_logged_in(page):
                        current_url = page.url
                        print(f"\n✅ 检测到已进入企微后台: {current_url}")
                        print("   请按 Enter 保存会话\n")
                        detected.set()
                        return
                except Exception:
                    pass

        watcher = threading.Thread(target=watch_url, daemon=True)
        watcher.start()

        input("登录完成后按 Enter 键保存会话并关闭浏览器...")

        # 按 Enter 后再做一次检测
        try:
            current_url = page.url
            print(f"\n当前 URL: {current_url}")

            if _is_logged_in(page):
                logger.info("✅ 会话已保存到 browser_data/ 目录")
                logger.info("   现在可以运行: python main.py")
            else:
                # 最后兜底：只要 URL 不是纯登录页就认为成功
                # （有时后台加载慢，DOM 还没渲染完）
                if "work.weixin.qq.com" in current_url and "loginpage_wx" not in current_url:
                    logger.info("✅ 会话已保存到 browser_data/ 目录（URL 已离开登录页）")
                    logger.info("   现在可以运行: python main.py")
                else:
                    logger.warning("⚠️  当前仍在登录页，会话可能未保存成功")
                    logger.warning("   请重新运行 save_cookie.py，确保扫码并在手机上确认登录后再按 Enter")
        except Exception as e:
            logger.info(f"会话已保存（URL 读取异常: {e}）")

        browser.close()


if __name__ == "__main__":
    save_session()
