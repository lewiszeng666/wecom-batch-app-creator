"""调试2：获取可见范围区域完整 HTML（英文界面）"""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = None
    for pg in context.pages:
        if "work.weixin.qq.com" in pg.url:
            page = pg
            break
    if not page:
        page = context.new_page()

    page.goto("https://work.weixin.qq.com/wework_admin/frame#/apps/createApiApp", wait_until="domcontentloaded")
    time.sleep(4)

    # 获取完整表单 HTML（后半部分，包含可见范围）
    html = page.evaluate("""
        () => {
            var form = document.querySelector('form.js_createApp_form');
            if (!form) return 'form not found';
            return form.outerHTML;
        }
    """)
    # 找可见范围部分
    idx = html.find('Visible')
    if idx == -1:
        idx = html.find('visible')
    if idx == -1:
        idx = html.find('Select')
    
    print("Form length:", len(html))
    print("Visible section (around index", idx, "):")
    print(html[max(0, idx-100):idx+1000])

    # 找所有 a 和 button 元素
    btns = page.evaluate("""
        () => {
            var results = [];
            var els = document.querySelectorAll('a, button');
            for (var el of els) {
                var t = el.textContent.trim();
                if (t && t.length < 20) {
                    results.push({tag: el.tagName, id: el.id, class: el.className.substring(0,60), text: t});
                }
            }
            return results;
        }
    """)
    print("\n所有短文本按钮:")
    for b in btns:
        print(" ", b)

    browser.close()
