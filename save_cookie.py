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
import select
import sys
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
    """判断当前页是否已进入企微后台（严格模式，避免误判）。"""
    try:
        url = (page.url or "").lower()
        if "work.weixin.qq.com" not in url:
            return False
        if "loginpage" in url or "login" in url:
            return False
        if "/wework_admin/frame" not in url:
            return False

        # 要求出现后台容器特征，避免仅凭 URL 误判
        has_backend = page.evaluate("""
            () => {
                var selectors = [
                    'iframe#main_frame', '#js_main', '.ww_nav', '.js_leftNav',
                    '#js_sidebar', '.frame_nav', '[class*="leftNav"]',
                    '.js_indexPage', '#js_frame'
                ];
                for (var s of selectors) {
                    if (document.querySelector(s)) return true;
                }
                return false;
            }
        """)
        return bool(has_backend)
    except Exception:
        return False


def _verify_session_by_backend_redirect(browser_context) -> tuple:
    """主动探测会话是否可访问后台，返回 (是否成功, 最终URL)。"""
    probe_urls = [
        "https://work.weixin.qq.com/wework_admin/frame#index",
        "https://work.weixin.qq.com/wework_admin/frame#/apps/applist",
    ]
    last_url = ""

    for target in probe_urls:
        p = None
        try:
            p = browser_context.new_page()
            p.goto(target, wait_until="domcontentloaded")
            time.sleep(2)
            last_url = p.url
            if _is_logged_in(p):
                return True, last_url
        except Exception:
            pass
        finally:
            try:
                if p:
                    p.close()
            except Exception:
                pass

    return False, last_url


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

        print("开始监听登录状态（最长 5 分钟）...")
        print("提示：你可随时在终端按 Enter 手动继续，不必等满 5 分钟。")

        manual_continue_available = sys.stdin.isatty()
        login_ok = False

        # 先等 3 秒让页面加载，再检测一次（处理自动恢复登录态的场景）
        time.sleep(3)
        try:
            if _is_logged_in(page):
                current_url = page.url
                print(f"\n✅ 检测到已进入企微后台（自动恢复会话）: {current_url}")
                login_ok = True
        except Exception:
            pass

        if not login_ok:
            for _i in range(300):
                time.sleep(1)

                # 仅在交互终端里允许按 Enter 手动继续（避免阻塞）
                if manual_continue_available and select.select([sys.stdin], [], [], 0)[0]:
                    _ = sys.stdin.readline()
                    print("\n⌨️ 收到回车，继续保存会话...")
                    break

                try:
                    if _is_logged_in(page):
                        current_url = page.url
                        print(f"\n✅ 检测到已进入企微后台: {current_url}")
                        login_ok = True
                        break
                except Exception:
                    pass

            if not login_ok:
                if manual_continue_available:
                    print("\n⚠️  若你已完成扫码并进入后台，可直接按 Enter 继续保存会话。")
                    input("确认后按 Enter 保存会话并关闭浏览器...")
                else:
                    print("\n⚠️  当前为非交互环境，跳过手动 Enter 等待，继续尝试保存会话。")

        # 按 Enter 后做会话校验
        try:
            current_url = page.url
            print(f"\n当前 URL: {current_url}")

            # 优先用当前页判断（已加载完毕，最可靠）
            if _is_logged_in(page):
                logger.info("✅ 会话已保存到 browser_data/ 目录")
                logger.info("   现在可以运行: python main.py")
            else:
                # 当前页可能还在登录页，但 URL 已含 frame → 等一下再试
                url_lower = (current_url or "").lower()
                if "/wework_admin/frame" in url_lower and "login" not in url_lower:
                    # URL 已到后台，可能 DOM 还没渲染完，多等几秒
                    time.sleep(3)
                    page.reload(wait_until="domcontentloaded")
                    time.sleep(3)
                    if _is_logged_in(page):
                        logger.info("✅ 会话已保存到 browser_data/ 目录")
                        logger.info("   现在可以运行: python main.py")
                    else:
                        # 最后兜底：URL 已在后台就认为成功
                        logger.info("✅ 会话已保存到 browser_data/ 目录（URL 已在后台页面）")
                        logger.info("   现在可以运行: python main.py")
                else:
                    # 真的还在登录页
                    ok, probe_url = _verify_session_by_backend_redirect(browser)
                    if ok:
                        logger.info("✅ 会话已保存到 browser_data/ 目录")
                        logger.info("   现在可以运行: python main.py")
                    else:
                        logger.warning("⚠️  会话校验失败：尚未进入可用后台登录态")
                        logger.warning(f"   探测 URL: {probe_url or 'N/A'}")
                        logger.warning("   请重新运行 save_cookie.py，扫码后在手机上确认并进入后台页面")
        except Exception as e:
            logger.warning(f"⚠️  会话校验异常: {e}")

        browser.close()


if __name__ == "__main__":
    save_session()
