"""调试：测试在 CDP 连接模式下触发 Logo 弹窗的正确方式"""
import time
from playwright.sync_api import sync_playwright
from pathlib import Path

LOGO_PATH = str(Path("openclaw_logo.png").resolve())

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()

    page.goto(
        "https://work.weixin.qq.com/wework_admin/frame#/apps/createApiApp",
        wait_until="domcontentloaded",
    )
    time.sleep(3)
    print("frames:", [(f.name, f.url[:60]) for f in page.frames])

    # --- 检查弹窗初始状态 ---
    info = page.evaluate("""
        () => {
            var d = document.querySelector('#__dialog__avatarEditor__');
            if (!d) return 'not found';
            return {
                display: d.style.display,
                className: d.className,
                parentDisplay: d.parentElement ? d.parentElement.style.display : 'N/A'
            };
        }
    """)
    print("dialog before trigger:", info)

    # --- 方法1：点击相机图标包裹元素 ---
    cam_info = page.evaluate("""
        () => {
            var selectors = ['.ww_fileInputWrap', '.js_upload_logo', '.apps_logo_wrap',
                             '.ww_updatePic', '#apps_upload_logo_image'];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el) return 'found: ' + s + ' class=' + el.className;
            }
            return 'none found';
        }
    """)
    print("camera element:", cam_info)

    # --- 方法2：直接用 Playwright locator 点击相机图标 ---
    # 企微相机图标通常是 .ww_fileInputWrap 或包含 input 的父元素
    try:
        # 先找到 file input 的父元素并点击
        page.locator(".ww_fileInputWrap").first.click(timeout=3000)
        time.sleep(2)
        dialog_visible = page.locator("#__dialog__avatarEditor__").is_visible()
        print("After .ww_fileInputWrap click, dialog visible:", dialog_visible)
    except Exception as e:
        print("ww_fileInputWrap click failed:", e)

    # --- 检查弹窗状态 ---
    info2 = page.evaluate("""
        () => {
            var d = document.querySelector('#__dialog__avatarEditor__');
            if (!d) return 'not found';
            return {
                display: d.style.display,
                visible: d.offsetParent !== null,
                className: d.className
            };
        }
    """)
    print("dialog after trigger:", info2)

    # --- 如果弹窗可见，尝试注入文件 ---
    if page.locator("#__dialog__avatarEditor__").is_visible():
        print("弹窗已打开！尝试注入文件...")
        file_input = page.locator("#__dialog__avatarEditor__ input[type=file]").first
        print("file input count:", page.locator("#__dialog__avatarEditor__ input[type=file]").count())
        file_input.set_input_files(LOGO_PATH)
        time.sleep(3)
        cropper = page.locator("#__dialog__avatarEditor__ .cropper-container").count()
        print("cropper count:", cropper)
    else:
        # 方法3：用 jQuery trigger
        page.evaluate("""
            () => {
                var input = document.querySelector('#apps_upload_logo_image');
                if (input && window.$) {
                    $(input).trigger('click');
                    return 'jQuery trigger done';
                }
                return 'jQuery not available or input not found';
            }
        """)
        time.sleep(2)
        info3 = page.evaluate("""
            () => {
                var d = document.querySelector('#__dialog__avatarEditor__');
                return d ? {display: d.style.display, visible: d.offsetParent !== null} : 'not found';
            }
        """)
        print("dialog after jQuery trigger:", info3)

    browser.close()
