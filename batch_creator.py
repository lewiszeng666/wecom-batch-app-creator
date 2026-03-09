"""
wecom-batch-app-creator / batch_creator.py
企业微信批量创建应用核心模块

已在真实企微后台实测验证的完整流程：
  1. jQuery trigger 触发 showAvatarEditor 弹窗（不能用原生 click）
  2. set_input_files 向弹窗内 file input 注入 Logo
  3. 等待 cropper.js 初始化，jQuery 验证 Save 按钮可用
  4. 点击 Save，等待弹窗关闭
  5. 填写应用名/介绍，设置可见范围
  6. 点击创建应用，进入应用详情页
  7. 设置接收消息 API（随机生成 Token/AESKey，填写 URL）
  8. 触发 Secret 发送到管理员企微 App
"""

import json
import os
import re
import time
import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────
WECOM_BASE = "https://work.weixin.qq.com/wework_admin"
CREATE_APP_URL = f"{WECOM_BASE}/frame#apps/createApiApp"
DIALOG_SELECTOR = "#__dialog__avatarEditor__"
CROPPER_SELECTOR = f"{DIALOG_SELECTOR} .cropper-container"
SAVE_BTN_SELECTOR = f"{DIALOG_SELECTOR} .js_save"
FRAME_SELECTOR = "iframe#main_frame"


# ─────────────────────────────────────────────
# 辅助：等待 iframe 内容加载
# ─────────────────────────────────────────────
def _get_frame(page: Page, timeout: int = 15000):
    """等待并返回企微后台主 iframe。"""
    page.wait_for_selector(FRAME_SELECTOR, timeout=timeout)
    frame = page.frame(name="main_frame") or page.frames[1]
    return frame


def _wait_for_frame_url(page: Page, url_fragment: str, timeout: int = 15000):
    """等待 iframe src 包含指定片段。"""
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        for f in page.frames:
            if url_fragment in (f.url or ""):
                return f
        time.sleep(0.3)
    raise PWTimeout(f"等待 iframe URL 包含 '{url_fragment}' 超时")


# ─────────────────────────────────────────────
# 核心：上传 Logo（已实测验证）
# ─────────────────────────────────────────────
def upload_logo(page: Page, logo_path: str) -> bool:
    """
    向企微创建应用页面上传 Logo。
    必须在 frame#apps/createApiApp 页面调用。

    Returns:
        True 表示上传成功（弹窗已关闭，Logo 已显示）
    """
    abs_logo = str(Path(logo_path).resolve())
    logger.info(f"开始上传 Logo: {abs_logo}")

    # 步骤1：jQuery trigger 触发 showAvatarEditor 弹窗
    # 不能用原生 click，企微用 Backbone 事件委托 + preventDefault 拦截了原生事件
    page.evaluate("""
        () => {
            var input = document.querySelector('#apps_upload_logo_image');
            if (input) {
                $(input).trigger('click');
            } else {
                var view = window._apiAppCreateView;
                if (view && view.showAvatarEditor) view.showAvatarEditor();
            }
        }
    """)
    time.sleep(1)

    # 步骤2：等待弹窗出现
    # 注意：企微弹窗从页面加载起就存在于 DOM（display:''），
    # Playwright 的 is_visible() 受遮挡影响可能误判，改用 JS offsetParent 判断
    dialog_ready = False
    for _ in range(10):
        ready = page.evaluate(f"""
            () => {{
                var d = document.querySelector('{DIALOG_SELECTOR}');
                return d !== null && d.offsetParent !== null;
            }}
        """)
        if ready:
            dialog_ready = True
            break
        time.sleep(0.5)

    if not dialog_ready:
        logger.error("等待编辑 Logo 弹窗超时")
        return False
    logger.info("编辑 Logo 弹窗已出现")

    # 步骤3：判断弹窗状态（初始/已有图），选择正确的 file input
    time.sleep(0.3)
    has_existing = page.evaluate(f"""
        () => {{
            var d = document.querySelector('{DIALOG_SELECTOR}');
            if (!d) return false;
            var noImg = d.querySelector('.js_no_img');
            var imgContainer = d.querySelector('.js_img_container');
            if (noImg && noImg.style.display !== 'none') return false;
            if (imgContainer && imgContainer.style.display !== 'none') return true;
            return false;
        }}
    """)

    if has_existing:
        # 已有图状态：Upload again 按钮内的 file input
        file_input_selector = f"{DIALOG_SELECTOR} .js_file_reupload .js_file"
        logger.info("弹窗状态：已有图，使用 Upload again file input")
    else:
        # 初始状态：选择图片按钮内的 file input
        file_input_selector = f"{DIALOG_SELECTOR} .js_no_img .ww_fileInput"
        logger.info("弹窗状态：初始，使用选择图片 file input")

    # 等待 file input 出现
    try:
        page.wait_for_selector(file_input_selector, timeout=3000)
    except PWTimeout:
        # 兜底：尝试任意弹窗内的 file input
        file_input_selector = f"{DIALOG_SELECTOR} input[type=file]"
        logger.warning(f"精确 file input 未找到，使用兜底选择器: {file_input_selector}")

    # 步骤4：注入文件（CDP set_input_files，正确触发 change 事件）
    try:
        page.locator(file_input_selector).set_input_files(abs_logo)
        logger.info("文件注入成功")
    except Exception as e:
        logger.error(f"文件注入失败: {e}")
        return False

    # 步骤5：等待 cropper.js 初始化
    try:
        page.wait_for_selector(CROPPER_SELECTOR, timeout=8000)
        logger.info("cropper.js 初始化完成")
    except PWTimeout:
        logger.warning("等待 cropper 超时，继续尝试保存")

    time.sleep(1.5)  # 等待 cropper 渲染稳定

    # 步骤6：验证 Save 按钮已启用（jQuery disabled 检测）
    for _ in range(10):
        save_enabled = page.evaluate(f"""
            () => {{
                var btn = document.querySelector('{SAVE_BTN_SELECTOR}');
                if (!btn) return false;
                return $(btn).attr('disabled') === undefined;
            }}
        """)
        if save_enabled:
            break
        time.sleep(0.5)
    else:
        logger.warning("Save 按钮仍为 disabled，强制继续")

    # 步骤7：点击 Save
    # 企微弹窗内元素可能被其他层遮挡，Playwright 的 click() 会因“元素被遮挡”报错
    # 改用 JS 直接调用 click() 方法，绕过可见性检查
    try:
        clicked = page.evaluate(f"""
            () => {{
                var btn = document.querySelector('{SAVE_BTN_SELECTOR}');
                if (!btn) return false;
                btn.click();
                return true;
            }}
        """)
        if clicked:
            logger.info("已点击 Save 按鈕")
        else:
            logger.error("Save 按鈕未找到")
            return False
    except Exception as e:
        logger.error(f"点击 Save 失败: {e}")
        return False

    # 步骤8：等待弹窗关闭（用 offsetParent 判断，不用 Playwright state='hidden'）
    for _ in range(30):  # 最多等 15 秒
        closed = page.evaluate(f"""
            () => {{
                var d = document.querySelector('{DIALOG_SELECTOR}');
                return d === null || d.offsetParent === null;
            }}
        """)
        if closed:
            logger.info("Logo 上传成功，弹窗已关闭")
            return True
        time.sleep(0.5)

    logger.error("等待弹窗关闭超时，Logo 上传可能失败")
    return False


# ─────────────────────────────────────────────
# 核心：设置可见范围
# ─────────────────────────────────────────────
def set_visible_range(page: Page, member_name: str) -> bool:
    """
    在创建应用表单中设置可见范围为指定成员。
    点击「选择部门/成员」按钮 → 搜索成员 → 勾选 → 确认。

    已验证的真实 DOM：
      - 触发按钮 class: js_show_visible_add
      - 文本（中文）: 选择部门/成员
      - 文本（英文）: Select departments/members
    """
    logger.info(f"设置可见范围: {member_name}")

    # 步骤1：点击可见范围「选择部门/成员」按钮
    # 优先用真实 class（已验证），备用文本匹配
    clicked = page.evaluate("""
        () => {
            // 优先用已验证的 class
            var btn = document.querySelector('.js_show_visible_add');
            if (btn) { btn.click(); return true; }
            // 备用：文本匹配（中英文）
            var links = document.querySelectorAll('a, button');
            for (var l of links) {
                var t = l.textContent.trim();
                if (t.includes('\u9009\u62e9\u90e8\u95e8') || t.includes('\u9009\u62e9\u6210\u5458')
                    || t === '\u9009\u62e9' || t === 'Select'
                    || t.includes('Select departments') || t.includes('Select members')) {
                    l.click();
                    return true;
                }
            }
            return false;
        }
    """)

    if not clicked:
        logger.error("未找到可见范围选择按钮")
        return False

    # 步骤2：等待成员选择弹窗
    # 企微成员选择弹窗的真实 class 包含 ww_dialog 或 qui_dialog
    dialog_appeared = False
    for _ in range(20):
        appeared = page.evaluate("""
            () => {
                // 找包含搜索框的弹窗
                var inputs = document.querySelectorAll('input[placeholder]');
                for (var inp of inputs) {
                    var ph = inp.placeholder;
                    if (ph.includes('\u641c\u7d22') || ph.includes('Search')) {
                        var parent = inp;
                        for (var i = 0; i < 6; i++) {
                            parent = parent.parentElement;
                            if (!parent) break;
                            if (parent.offsetParent !== null) return true;
                        }
                    }
                }
                return false;
            }
        """)
        if appeared:
            dialog_appeared = True
            break
        time.sleep(0.3)

    if not dialog_appeared:
        logger.warning("成员选择弹窗未出现，尝试继续")

    time.sleep(0.5)

    # 步骤3：在搜索框输入成员名
    try:
        page.evaluate(f"""
            () => {{
                var inputs = document.querySelectorAll('input[placeholder]');
                for (var inp of inputs) {{
                    var ph = inp.placeholder;
                    if (ph.includes('\\u641c\\u7d22') || ph.includes('Search')) {{
                        // 确认是可见的搜索框
                        if (inp.offsetParent !== null) {{
                            inp.value = '{member_name}';
                            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                            inp.dispatchEvent(new Event('keyup', {{bubbles: true}}));
                            return;
                        }}
                    }}
                }}
            }}
        """)
        time.sleep(1.5)  # 等待搜索结果渲染
    except Exception as e:
        logger.warning(f"搜索框操作失败: {e}")

    # 步骤4：勾选成员（点击包含成员名的列表项）
    try:
        page.evaluate(f"""
            () => {{
                // 找搜索结果列表中包含成员名的项
                var items = document.querySelectorAll(
                    '.member_item, .ww_member_item, .js_member_item, '
                    + '.qui_listItem, [class*="member"][class*="item"], '
                    + '.ww_groupSelBtn_item, li'
                );
                for (var item of items) {{
                    if (item.textContent.includes('{member_name}') && item.offsetParent !== null) {{
                        item.click();
                        return;
                    }}
                }}
                // 兜底：找所有包含成员名且可见的元素
                var all = document.querySelectorAll('*');
                for (var el of all) {{
                    if (el.children.length === 0
                        && el.textContent.trim() === '{member_name}'
                        && el.offsetParent !== null) {{
                        el.click();
                        return;
                    }}
                }}
            }}
        """)
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"勾选成员失败: {e}")

    # 步骤5：点击确认按钮（中英文兼容）
    page.evaluate("""
        () => {
            var btns = document.querySelectorAll('button, a');
            for (var b of btns) {
                var t = b.textContent.trim();
                // 精确匹配确认/确定/Confirm/OK
                if ((t === '\u786e\u5b9a' || t === '\u786e\u8ba4'
                     || t === 'Confirm' || t === 'OK')
                    && b.offsetParent !== null) {
                    b.click();
                    return;
                }
            }
        }
    """)

    time.sleep(0.8)
    logger.info(f"可见范围设置完成: {member_name}")
    return True


# ─────────────────────────────────────────────
# 核心：创建单个应用
# ─────────────────────────────────────────────
def create_single_app(
    page: Page,
    app_number: int,
    app_name_prefix: str,
    app_description: str,
    logo_path: str,
    visible_member: str,
    openclaw_ip: str,
) -> dict:
    """
    创建单个企微应用，完成 API 接收消息配置。

    Returns:
        dict: {
            "success": bool,
            "app_name": str,
            "corp_id": str,
            "agent_id": str,
            "secret": "xxx",
            "token": str,
            "aes_key": str,
            "webhook_url": str,
            "error": str (仅失败时)
        }
    """
    app_name = f"{app_number}号{app_name_prefix}"
    result = {
        "success": False,
        "app_name": app_name,
        "corp_id": "",
        "agent_id": "",
        "secret": "xxx",
        "token": "",
        "aes_key": "",
        "webhook_url": f"http://{openclaw_ip}:3000/wecom",
    }

    logger.info(f"═══ 开始创建应用: {app_name} ═══")

    # ── 导航到创建应用页面 ──
    page.goto(CREATE_APP_URL, wait_until="domcontentloaded")
    time.sleep(2)

    # 等待页面内容加载（企微是 SPA，URL hash 变化后需等待 JS 渲染）
    try:
        page.wait_for_selector("#apps_upload_logo_image, .js_app_logo", timeout=15000)
    except PWTimeout:
        # 尝试等待 iframe
        try:
            frame = _get_frame(page, timeout=10000)
            frame.wait_for_selector("#apps_upload_logo_image", timeout=10000)
            logger.info("在 iframe 中找到表单")
        except Exception:
            logger.error("创建应用页面加载失败")
            result["error"] = "页面加载失败"
            return result

    # ── 填写应用名称 ──
    logger.info(f"填写应用名称: {app_name}")
    try:
        page.evaluate(f"""
            () => {{
                var nameInput = document.querySelector('#apps_name, input[name="name"], .js_app_name input');
                if (!nameInput) {{
                    // 尝试 iframe
                    var frames = document.querySelectorAll('iframe');
                    for (var f of frames) {{
                        try {{
                            nameInput = f.contentDocument.querySelector('#apps_name, .js_app_name input');
                            if (nameInput) break;
                        }} catch(e) {{}}
                    }}
                }}
                if (nameInput) {{
                    nameInput.value = '{app_name}';
                    nameInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                    nameInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}
        """)
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"填写应用名称失败: {e}")

    # ── 填写应用介绍 ──
    logger.info(f"填写应用介绍: {app_description}")
    try:
        page.evaluate(f"""
            () => {{
                var descInput = document.querySelector('#apps_desc, textarea[name="desc"], .js_app_desc textarea, .js_app_desc input');
                if (!descInput) {{
                    var frames = document.querySelectorAll('iframe');
                    for (var f of frames) {{
                        try {{
                            descInput = f.contentDocument.querySelector('#apps_desc, .js_app_desc textarea');
                            if (descInput) break;
                        }} catch(e) {{}}
                    }}
                }}
                if (descInput) {{
                    descInput.value = '{app_description}';
                    descInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                    descInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}
        """)
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"填写应用介绍失败: {e}")

    # ── 上传 Logo ──
    logo_ok = upload_logo(page, logo_path)
    if not logo_ok:
        logger.error("Logo 上传失败，跳过此应用")
        result["error"] = "Logo 上传失败"
        return result

    # ── 设置可见范围 ──
    visible_ok = set_visible_range(page, visible_member)
    if not visible_ok:
        logger.warning("可见范围设置可能未成功，继续尝试创建")

    # ── 点击创建应用 ──
    logger.info("点击创建应用按钮")
    try:
        page.evaluate("""
            () => {
                // 优先用已验证的 class
                var btn = document.querySelector(
                    '.js_create_app, .apiApp_create_submitBtn, .js_submit_app'
                );
                if (!btn) {
                    // 备用：文本匹配（中英文）
                    var btns = document.querySelectorAll('a, button');
                    for (var b of btns) {
                        var t = b.textContent.trim();
                        if (t === '创建应用' || t === 'Create an app'
                            || t.includes('创建应用') || t === 'Create') {
                            btn = b;
                            break;
                        }
                    }
                }
                if (btn) btn.click();
            }
        """)
        time.sleep(2)
    except Exception as e:
        logger.error(f"点击创建应用失败: {e}")
        result["error"] = "点击创建应用失败"
        return result

    # ── 等待跳转到应用详情页 ──
    logger.info("等待跳转到应用详情页...")
    agent_id = None
    for _ in range(30):
        current_url = page.url
        # 匹配 modApiApp/{agent_id} 格式
        m = re.search(r'modApiApp[/#](\d+)', current_url)
        if m:
            agent_id = m.group(1)
            break
        # 检查 iframe URL
        for f in page.frames:
            m = re.search(r'modApiApp[/#](\d+)', f.url or "")
            if m:
                agent_id = m.group(1)
                break
        if agent_id:
            break
        time.sleep(1)

    if not agent_id:
        # 尝试从页面内容提取 AgentId
        try:
            agent_id = page.evaluate("""
                () => {
                    var el = document.querySelector('.js_agent_id, [data-agentid]');
                    if (el) return el.textContent.trim() || el.getAttribute('data-agentid');
                    // 从 URL hash 提取
                    var m = location.hash.match(/modApiApp[/#](\d+)/);
                    return m ? m[1] : null;
                }
            """)
        except Exception:
            pass

    if not agent_id:
        logger.error("未能获取 AgentId，应用创建可能失败")
        # 检查是否有错误提示
        error_msg = page.evaluate("""
            () => {
                var err = document.querySelector('.error_msg, .js_error, .ww_form_error');
                return err ? err.textContent.trim() : '';
            }
        """)
        result["error"] = f"未获取到 AgentId，页面提示: {error_msg}"
        return result

    logger.info(f"应用创建成功，AgentId: {agent_id}")
    result["agent_id"] = agent_id

    # ── 获取 CORP_ID ──
    try:
        corp_id = page.evaluate("""
            () => {
                // 从 cookie 或页面全局变量获取 corpid
                var match = document.cookie.match(/wwmng_corpid=([^;]+)/);
                if (match) return decodeURIComponent(match[1]);
                if (window.corpid) return window.corpid;
                if (window.wx && window.wx.corpid) return window.wx.corpid;
                return '';
            }
        """)
        result["corp_id"] = corp_id or ""
    except Exception:
        pass

    # ── 进入接收消息 API 设置页面 ──
    logger.info("进入接收消息 API 设置...")
    try:
        # 点击「接收消息」或「Receive Messages」
        page.evaluate("""
            () => {
                var links = document.querySelectorAll('a, .js_link, .menu_item, li, .tab_item');
                for (var l of links) {
                    var t = l.textContent.trim();
                    if ((t.includes('接收消息') || t.includes('Receive Messages')
                         || t.includes('Receive Message'))
                        && l.offsetParent !== null) {
                        l.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1.5)

        # 点击「设置API接收」或「Set to receive messages via API」
        page.evaluate("""
            () => {
                var links = document.querySelectorAll('a, button, .js_link, span');
                for (var l of links) {
                    var t = l.textContent.trim();
                    if ((t.includes('设置API接收') || t.includes('设置 API 接收')
                         || t.includes('Set to receive') || t.includes('Set API')
                         || t.includes('API接收') || t.includes('via API'))
                        && l.offsetParent !== null) {
                        l.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(2)
    except Exception as e:
        logger.warning(f"进入接收消息设置失败: {e}")

    # ── 等待 API 接收设置页面加载 ──
    # 已验证的真实 input ID: #inner_app_token, #inner_app_AES, #inner_app_apiurl
    try:
        page.wait_for_selector(
            '#inner_app_token, input[name="url_token"]',
            timeout=10000
        )
        logger.info("API 接收设置页面已加载")
    except PWTimeout:
        logger.warning("API 接收设置页面可能未正确加载")

    time.sleep(1)

    # ── 随机生成 Token ──
    # 已验证：第一个 'Get randomly' 按鈕 class=js_resetUrlToken
    logger.info("随机生成 Token...")
    try:
        page.evaluate("""
            () => {
                // 优先用已验证的 class
                var btn = document.querySelector('.js_resetUrlToken');
                if (btn) { btn.click(); return; }
                // 备用：第一个「随机生成」/「Get randomly」按鈕
                var btns = document.querySelectorAll('a, button');
                for (var b of btns) {
                    var txt = b.textContent.trim();
                    if ((txt === '随机生成' || txt === 'Get randomly')
                        && b.offsetParent !== null) {
                        b.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(0.8)
    except Exception as e:
        logger.warning(f"随机生成 Token 失败: {e}")

    # ── 随机生成 EncodingAESKey ──
    # 已验证：第二个 'Get randomly' 按鈕 class=js_resetAESKey
    logger.info("随机生成 EncodingAESKey...")
    try:
        page.evaluate("""
            () => {
                // 优先用已验证的 class
                var btn = document.querySelector('.js_resetAESKey');
                if (btn) { btn.click(); return; }
                // 备用：第二个「随机生成」/「Get randomly」按鈕
                var btns = document.querySelectorAll('a, button');
                var found = 0;
                for (var b of btns) {
                    var txt = b.textContent.trim();
                    if ((txt === '随机生成' || txt === 'Get randomly')
                        && b.offsetParent !== null) {
                        found++;
                        if (found === 2) { b.click(); return; }
                    }
                }
            }
        """)
        time.sleep(0.8)
    except Exception as e:
        logger.warning(f"随机生成 EncodingAESKey 失败: {e}")

    # ── 填写 URL ──
    # 已验证的真实 ID: #inner_app_apiurl， name=callback_url
    webhook_url = f"http://{openclaw_ip}:3000/wecom"
    logger.info(f"填写 URL: {webhook_url}")
    try:
        page.evaluate(f"""
            () => {{
                var urlInput = document.querySelector(
                    '#inner_app_apiurl, input[name="callback_url"]'
                );
                if (urlInput) {{
                    urlInput.value = '{webhook_url}';
                    urlInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                    urlInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}
        """)
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"填写 URL 失败: {e}")

    # ── 读取生成的 Token 和 EncodingAESKey ──
    # 已验证的真实 ID: #inner_app_token, #inner_app_AES
    time.sleep(0.5)
    try:
        values = page.evaluate("""
            () => {
                var result = {token: '', aes_key: '', url: ''};
                // 优先用已验证的真实 ID
                var tokenInp = document.querySelector('#inner_app_token, input[name="url_token"]');
                var aesInp   = document.querySelector('#inner_app_AES, input[name="callback_aeskey"]');
                var urlInp   = document.querySelector('#inner_app_apiurl, input[name="callback_url"]');
                if (tokenInp) result.token   = tokenInp.value.trim();
                if (aesInp)   result.aes_key = aesInp.value.trim();
                if (urlInp)   result.url     = urlInp.value.trim();
                return result;
            }
        """)
        if values.get("token"):
            result["token"] = values["token"]
        if values.get("aes_key"):
            result["aes_key"] = values["aes_key"]
        logger.info(f"Token: {result['token'][:8]}..." if result['token'] else "Token: 未获取")
        logger.info(f"AESKey: {result['aes_key'][:8]}..." if result['aes_key'] else "AESKey: 未获取")
    except Exception as e:
        logger.warning(f"读取 Token/AESKey 失败: {e}")

    # ── 触发 Secret 发送到企微 App ──
    logger.info("触发 Secret 发送到管理员企微 App...")
    try:
        # 先点击保存（会失败，因为 URL 验证不通过，但 Token/AESKey 已记录）
        page.evaluate("""
            () => {
                var btns = document.querySelectorAll('button, .btn');
                for (var b of btns) {
                    if (b.textContent.includes('保存') || b.textContent.includes('Save')) {
                        b.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1)
    except Exception:
        pass

    # 回到应用详情页触发 Secret 发送
    try:
        page.goto(f"{WECOM_BASE}/frame#apps/modApiApp/{agent_id}", wait_until="domcontentloaded")
        time.sleep(2)

        # 点击 View Secret → Send
        page.evaluate("""
            () => {
                var links = document.querySelectorAll('a, button, span');
                for (var l of links) {
                    if (l.textContent.includes('查看') || l.textContent.includes('View')) {
                        l.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1)

        page.evaluate("""
            () => {
                var btns = document.querySelectorAll('button, a');
                for (var b of btns) {
                    if (b.textContent.includes('发送') || b.textContent.includes('Send')) {
                        b.click();
                        return;
                    }
                }
            }
        """)
        time.sleep(1)
        logger.info("Secret 发送触发完成，请在企微 App 查看")
    except Exception as e:
        logger.warning(f"触发 Secret 发送失败: {e}")

    result["success"] = True
    logger.info(f"═══ 应用 {app_name} 创建完成 ═══")
    return result


# ─────────────────────────────────────────────
# 主入口：批量创建
# ─────────────────────────────────────────────
class BatchAppCreator:
    """企业微信批量创建应用工具。"""

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.corp_id = self.config["corp_id"]
        self.visible_member = self.config["visible_member"]
        self.create_count = int(self.config["create_count"])
        self.openclaw_ip = self.config["openclaw_ip"]
        self.app_name_prefix = self.config.get("app_name_prefix", "openclaw")
        self.app_description = self.config.get("app_description", "与openclaw通信通道")
        self.logo_path = self.config.get("logo_path", "openclaw_logo.png")
        self.output_file = self.config.get("output_file", "output/app_configs.json")
        self.headless = self.config.get("headless", True)
        self.browser_data_dir = self.config.get("browser_data_dir", "browser_data")

        # 确保输出目录存在
        Path(self.output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.browser_data_dir).mkdir(parents=True, exist_ok=True)

        self._playwright = None
        self._browser = None
        self._page = None

    def _get_existing_app_numbers(self) -> set:
        """从输出文件读取已创建的应用编号，避免重复。"""
        if not Path(self.output_file).exists():
            return set()
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            numbers = set()
            for item in data:
                name = item.get("app_name", "")
                m = re.match(r"^(\d+)号", name)
                if m:
                    numbers.add(int(m.group(1)))
            return numbers
        except Exception:
            return set()

    def _save_result(self, result: dict):
        """追加保存单个应用配置到输出文件。"""
        existing = []
        if Path(self.output_file).exists():
            try:
                with open(self.output_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing.append(result)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info(f"配置已保存到 {self.output_file}")

    def _print_result(self, result: dict):
        """打印单个应用配置到控制台。"""
        print("\n" + "═" * 60)
        print(f"  应用名称: {result['app_name']}")
        print("═" * 60)
        print(f"  CORP_ID:         {result['corp_id']}")
        print(f"  AgentId:         {result['agent_id']}")
        print(f"  Secret:          {result['secret']}  ← 请在企微 App 查看后手工填入")
        print(f"  Token:           {result['token']}")
        print(f"  EncodingAESKey:  {result['aes_key']}")
        print(f"  Webhook URL:     {result['webhook_url']}")
        print("═" * 60 + "\n")

    def start_browser(self):
        """启动浏览器。

        优先尝试通过 CDP 连接到已有浏览器（沙箱/CI 环境）；
        若 CDP 不可用，则用 launch_persistent_context 启动新浏览器（本地环境）。
        """
        self._playwright = sync_playwright().start()
        cdp_url = self.config.get("cdp_url", "http://127.0.0.1:9222")

        # 优先尝试 CDP 连接
        try:
            import urllib.request
            urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2)
            browser = self._playwright.chromium.connect_over_cdp(cdp_url)
            self._context = browser.contexts[0]
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._browser = browser
            logger.info(f"已通过 CDP 连接到已有浏览器 ({cdp_url})")
            return
        except Exception:
            logger.info("CDP 不可用，使用 launch_persistent_context 启动新浏览器")

        # 备用：launch_persistent_context（本地环境）
        # 自动检测可用的 Chromium 路径
        import shutil
        chromium_path = None
        for candidate in [
            shutil.which("chromium-browser"),
            shutil.which("chromium"),
            shutil.which("google-chrome"),
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]:
            if candidate and Path(candidate).exists():
                chromium_path = candidate
                break

        launch_kwargs = dict(
            user_data_dir=str(Path(self.browser_data_dir).resolve()),
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        if chromium_path:
            launch_kwargs["executable_path"] = chromium_path
            logger.info(f"使用 Chromium: {chromium_path}")

        self._browser = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        self._page = self._browser.pages[0] if self._browser.pages else self._browser.new_page()
        logger.info(f"浏览器已启动 (headless={self.headless})")

    def close_browser(self):
        """关闭浏览器。"""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def check_login(self) -> bool:
        """检查企微后台登录状态。"""
        self._page.goto(f"{WECOM_BASE}/frame#index", wait_until="domcontentloaded")
        time.sleep(2)
        current_url = self._page.url
        if "loginpage" in current_url or "login" in current_url.lower():
            logger.error("企微后台未登录，请先运行 save_cookie.py 完成扫码登录")
            return False
        logger.info("企微后台登录状态正常")
        return True

    def run(self) -> list:
        """
        执行批量创建。

        Returns:
            list: 所有成功创建的应用配置列表
        """
        self.start_browser()

        if not self.check_login():
            self.close_browser()
            raise RuntimeError("企微后台未登录，请先运行 save_cookie.py")

        # 计算起始编号（避免与已有应用重复）
        existing_numbers = self._get_existing_app_numbers()
        logger.info(f"已有应用编号: {sorted(existing_numbers)}")

        next_number = 1
        created_count = 0
        all_results = []

        while created_count < self.create_count:
            # 找下一个未使用的编号
            while next_number in existing_numbers:
                next_number += 1

            result = create_single_app(
                page=self._page,
                app_number=next_number,
                app_name_prefix=self.app_name_prefix,
                app_description=self.app_description,
                logo_path=self.logo_path,
                visible_member=self.visible_member,
                openclaw_ip=self.openclaw_ip,
            )

            if result["success"]:
                # 补充 corp_id（如果页面没读到，使用配置值）
                if not result["corp_id"]:
                    result["corp_id"] = self.corp_id

                self._save_result(result)
                self._print_result(result)
                all_results.append(result)
                existing_numbers.add(next_number)
                created_count += 1
            else:
                logger.error(f"应用 {next_number}号{self.app_name_prefix} 创建失败: {result.get('error', '未知错误')}")

            next_number += 1

        self.close_browser()

        print(f"\n✅ 批量创建完成，共创建 {created_count} 个应用")
        print(f"📄 配置已保存到: {self.output_file}")
        print("⚠️  请在企微 App 查看各应用的 Secret，手工填入 output/app_configs.json 中的 'secret' 字段\n")

        return all_results
