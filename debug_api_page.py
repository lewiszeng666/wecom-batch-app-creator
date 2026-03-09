"""调试：检查 API 接收设置页面的真实 input 结构"""
import time
from playwright.sync_api import sync_playwright

AGENT_ID = "5629500952680377"  # 刚创建的应用

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

    # 导航到应用详情页
    page.goto(f"https://work.weixin.qq.com/wework_admin/frame#apps/modApiApp/{AGENT_ID}",
              wait_until="domcontentloaded")
    time.sleep(3)
    print("URL:", page.url)

    # 检查接收消息相关链接
    links = page.evaluate("""
        () => {
            var results = [];
            var els = document.querySelectorAll('a, button, li, .tab_item, [class*="tab"]');
            for (var el of els) {
                var t = el.textContent.trim();
                if (t && t.length < 30 && el.offsetParent !== null) {
                    results.push({tag: el.tagName, class: el.className.substring(0,50), text: t});
                }
            }
            return results;
        }
    """)
    print("\n可见链接/按钮:")
    for l in links:
        print(" ", l)

    # 点击接收消息
    page.evaluate("""
        () => {
            var links = document.querySelectorAll('a, .js_link, .menu_item, li, .tab_item');
            for (var l of links) {
                var t = l.textContent.trim();
                if ((t.includes('接收消息') || t.includes('Receive Messages')
                     || t.includes('Receive Message'))
                    && l.offsetParent !== null) {
                    console.log('Clicking:', t, l.className);
                    l.click();
                    return;
                }
            }
        }
    """)
    time.sleep(2)

    # 点击设置API接收
    page.evaluate("""
        () => {
            var links = document.querySelectorAll('a, button, .js_link, span');
            for (var l of links) {
                var t = l.textContent.trim();
                if ((t.includes('设置API接收') || t.includes('设置 API 接收')
                     || t.includes('Set to receive') || t.includes('Set API')
                     || t.includes('API接收') || t.includes('via API'))
                    && l.offsetParent !== null) {
                    console.log('Clicking API btn:', t);
                    l.click();
                    return;
                }
            }
        }
    """)
    time.sleep(2)

    # 检查当前页面所有 input
    inputs = page.evaluate("""
        () => {
            var results = [];
            var inputs = document.querySelectorAll('input, textarea');
            for (var inp of inputs) {
                results.push({
                    tag: inp.tagName,
                    type: inp.type,
                    name: inp.name,
                    id: inp.id,
                    placeholder: inp.placeholder,
                    value: inp.value.substring(0, 30),
                    class: inp.className.substring(0, 50),
                    visible: inp.offsetParent !== null
                });
            }
            return results;
        }
    """)
    print("\n所有 input:")
    for inp in inputs:
        print(" ", inp)

    page.screenshot(path="debug_api_page.png")
    print("\n截图: debug_api_page.png")
    browser.close()
