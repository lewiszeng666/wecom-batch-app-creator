"""调试2：弹窗已存在，直接注入文件测试完整 Logo 上传流程"""
import time
from playwright.sync_api import sync_playwright
from pathlib import Path

LOGO_PATH = str(Path("openclaw_logo.png").resolve())
DIALOG = "#__dialog__avatarEditor__"
CROPPER = f"{DIALOG} .cropper-container"
SAVE_BTN = f"{DIALOG} .js_save"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()

    page.goto(
        "https://work.weixin.qq.com/wework_admin/frame#/apps/createApiApp",
        wait_until="domcontentloaded",
    )
    time.sleep(3)

    # 检查弹窗状态（用 offsetParent 判断，更可靠）
    dialog_info = page.evaluate(f"""
        () => {{
            var d = document.querySelector('{DIALOG}');
            if (!d) return 'not found';
            return {{
                display: d.style.display,
                offsetParentNull: d.offsetParent === null,
                hasNoImg: !!d.querySelector('.js_no_img'),
                noImgDisplay: d.querySelector('.js_no_img') ? d.querySelector('.js_no_img').style.display : 'N/A',
                hasImgContainer: !!d.querySelector('.js_img_container'),
                fileInputCount: d.querySelectorAll('input[type=file]').length
            }};
        }}
    """)
    print("dialog info:", dialog_info)

    # 如果弹窗存在，直接找 file input 注入
    file_input_count = page.locator(f"{DIALOG} input[type=file]").count()
    print("file input count:", file_input_count)

    if file_input_count > 0:
        # 找到正确的 file input（js_no_img 里的，或任意可见的）
        # 先检查 js_no_img 状态
        no_img_display = page.evaluate(f"""
            () => {{
                var d = document.querySelector('{DIALOG}');
                var noImg = d ? d.querySelector('.js_no_img') : null;
                return noImg ? noImg.style.display : 'N/A';
            }}
        """)
        print("js_no_img display:", no_img_display)

        # 选择 file input
        if no_img_display != 'none':
            file_sel = f"{DIALOG} .js_no_img input[type=file]"
        else:
            file_sel = f"{DIALOG} .js_file_reupload input[type=file]"

        fi_count = page.locator(file_sel).count()
        print(f"file input ({file_sel}) count:", fi_count)

        if fi_count == 0:
            file_sel = f"{DIALOG} input[type=file]"
            print("fallback to any file input")

        # 注入文件
        print("注入文件:", LOGO_PATH)
        page.locator(file_sel).first.set_input_files(LOGO_PATH)
        time.sleep(3)

        # 检查 cropper
        cropper_count = page.locator(CROPPER).count()
        print("cropper count:", cropper_count)

        # 检查 Save 按钮状态
        save_enabled = page.evaluate(f"""
            () => {{
                var btn = document.querySelector('{SAVE_BTN}');
                if (!btn) return 'not found';
                return {{
                    disabled: btn.disabled,
                    jqDisabled: window.$ ? $(btn).attr('disabled') : 'N/A',
                    text: btn.textContent.trim()
                }};
            }}
        """)
        print("save btn:", save_enabled)

        if cropper_count > 0:
            time.sleep(1.5)
            # 点击 Save
            print("点击 Save 按钮...")
            page.locator(SAVE_BTN).click(timeout=5000)
            time.sleep(3)

            # 检查弹窗是否关闭
            dialog_after = page.evaluate(f"""
                () => {{
                    var d = document.querySelector('{DIALOG}');
                    return d ? {{display: d.style.display, offsetParentNull: d.offsetParent === null}} : 'not found';
                }}
            """)
            print("dialog after save:", dialog_after)

            # 检查 Logo 是否显示
            logo_img = page.evaluate("""
                () => {
                    var img = document.querySelector('.apps_logo_img, .js_logo_img, img.ww_logo');
                    return img ? img.src : 'not found';
                }
            """)
            print("logo img src:", logo_img[:80] if logo_img else 'N/A')

    browser.close()
    print("DONE")
