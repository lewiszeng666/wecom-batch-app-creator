"""调试：检查创建应用页面可见范围选择按钮的真实 DOM 结构"""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    # 找到企微后台页面
    page = None
    for pg in context.pages:
        if "work.weixin.qq.com" in pg.url:
            page = pg
            break
    if not page:
        page = context.new_page()

    page.goto("https://work.weixin.qq.com/wework_admin/frame#/apps/createApiApp", wait_until="domcontentloaded")
    time.sleep(4)
    print("Current URL:", page.url)

    # 获取整个表单区域的 HTML
    html = page.evaluate("""
        () => {
            // 找到创建应用表单
            var form = document.querySelector('form, .js_create_app_form, .create_app_form, #createApiAppForm');
            if (form) return form.outerHTML.substring(0, 3000);
            // 找包含 logo input 的父容器
            var logo = document.querySelector('#apps_upload_logo_image');
            if (logo) {
                var parent = logo.parentElement;
                for (var i = 0; i < 5; i++) {
                    if (parent && parent.tagName === 'FORM') return parent.outerHTML.substring(0, 3000);
                    if (parent) parent = parent.parentElement;
                }
                return logo.closest('form, [class*="form"]') ? logo.closest('form, [class*="form"]').outerHTML.substring(0, 3000) : 'no form found';
            }
            return 'no logo input found';
        }
    """)
    print("Form HTML:", html[:2000])

    # 专门找可见范围相关元素
    visible_info = page.evaluate("""
        () => {
            var all = document.querySelectorAll('*');
            var results = [];
            for (var el of all) {
                var text = el.textContent.trim();
                if ((text === '选择' || text === 'Select') && el.children.length === 0) {
                    results.push({
                        tag: el.tagName,
                        id: el.id,
                        className: el.className,
                        text: text,
                        parentClass: el.parentElement ? el.parentElement.className : '',
                        parentId: el.parentElement ? el.parentElement.id : ''
                    });
                }
            }
            return results;
        }
    """)
    print("\\n选择按钮:", visible_info)

    # 截图
    page.screenshot(path="debug_visible.png")
    print("截图已保存: debug_visible.png")
    browser.close()
