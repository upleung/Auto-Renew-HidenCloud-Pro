#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os,re,sys,time,random,requests
try:
    from patchright.sync_api import sync_playwright
    USING_PATCHRIGHT = True
except ImportError:
    from playwright.sync_api import sync_playwright
    USING_PATCHRIGHT = False

# --- 环境变量 ---
COOKIE_VALUE = os.environ.get('COOKIE_VALUE') or ""
EMAIL        = os.environ.get('EMAIL') or ""
PASSWORD     = os.environ.get('PASSWORD') or ""
TG_CHAT_ID   = os.environ.get('TG_CHAT_ID') or ""
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN') or ""

# --- 微信原生推送配置 ---
WECHAT_APPID       = os.environ.get('WECHAT_APPID') or ""
WECHAT_APPSECRET   = os.environ.get('WECHAT_APPSECRET') or ""
WECHAT_OPENID      = os.environ.get('WECHAT_OPENID') or ""
WECHAT_OPENID2     = os.environ.get('WECHAT_OPENID2') or ""
WECHAT_TEMPLATE_ID = os.environ.get('WECHAT_TEMPLATE_ID') or ""

BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"

# --- 代理配置 ---
IS_PROXY      = os.environ.get('IS_PROXY', 'false').lower() == 'true'
PROXY_SERVER  = os.environ.get('PROXY_SERVER') or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None

# Cloudflare 整页挑战 / Turnstile 组件共用的 iframe 选择器
CF_IFRAME_SELECTOR = 'iframe[src*="challenges.cloudflare.com"]'

# 按运行平台选择 UA
if sys.platform == 'win32':
    DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
else:
    DEFAULT_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time.time() + 8 * 3600))}] {message}", flush=True)

STEALTH_JS = """
try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
} catch (e) {}
"""

def get_current_ip(proxy_server=None):
    proxies = {"http": proxy_server, "https": proxy_server} if (proxy_server and IS_PROXY) else None
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
        if resp.status_code == 200:
            return resp.text.strip()
        return "获取失败"
    except Exception as e:
        log(f"❌ 获取出口IP失败: {e}")
        return "获取失败"

def format_push_content(status, old_due, new_due, current_ip="未知"):
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))
    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        masked_email = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****' if EMAIL else "未配置"

    return masked_email, now

def send_telegram_notification(status, old_due, new_due, current_ip="未知"):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ Telegram 未配置，跳过推送")
        return False
        
    masked_email, now = format_push_content(status, old_due, new_due, current_ip)
    text = (
        f"🎉 HidenCloud 续期通知\n\n"
        f"{status}\n"
        f"👤 账号: {masked_email}\n"
        f"📅 续期前到期：{old_due}\n"
        f"📅 续期后到期：{new_due}\n"
        f"🌐 续期使用IP: {current_ip}\n"
        f"🕒 续期时间：{now}"
    )
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10, proxies=REQUESTS_PROXIES)
        if resp.status_code == 200:
            log("✅ Telegram 通知发送成功")
            return True
        log(f"❌ Telegram 通知失败: {resp.text}")
    except Exception as e:
        log(f"❌ Telegram 通知异常: {e}")
    return False

def send_wechat_notification(status, old_due, new_due, current_ip="未知"):
    if not all([WECHAT_APPID, WECHAT_APPSECRET, WECHAT_TEMPLATE_ID]) or not (WECHAT_OPENID or WECHAT_OPENID2):
        log("⚠️ 微信直连推送参数未配置齐全，跳过推送")
        return False
        
    masked_email, now = format_push_content(status, old_due, new_due, current_ip)
    clean_status = status.replace("✅ ", "").replace("❌ ", "").replace("⏳ ", "")
    wechat_title = f"Hiden🌥 {clean_status}"

    wechat_content = (
        f"账号: {masked_email}\n"
        f"续期前: {old_due}\n"
        f"续期后: {new_due}\n"
        f"IP: {current_ip}\n"
        f"时间: {now}"
    )
    
    try:
        token_url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APPID}&secret={WECHAT_APPSECRET}"
        token_resp = requests.get(token_url, timeout=10).json()
        access_token = token_resp.get("access_token")
        if not access_token:
            log(f"❌ 获取微信 Access Token 失败")
            return False

        openids = [oid for oid in [WECHAT_OPENID, WECHAT_OPENID2] if oid]
        success_count = 0
        
        for openid in openids:
            push_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
            payload = {
                "touser": openid,
                "template_id": WECHAT_TEMPLATE_ID,
                "data": {
                    "title": {"value": wechat_title, "color": "#173177"},
                    "content": {"value": wechat_content, "color": "#333333"}
                }
            }
            push_resp = requests.post(push_url, json=payload, timeout=10).json()
            if push_resp.get("errcode") == 0:
                log(f"✅ 微信官方直连推送成功 (尾号 {openid[-4:]})")
                success_count += 1
            else:
                log(f"❌ 微信直连推送失败 (尾号 {openid[-4:]}): {push_resp}")
                
        return success_count > 0
    except Exception as e:
        log(f"❌ 微信直连推送请求异常: {e}")
        return False

def _get_turnstile_token(page):
    try:
        return page.evaluate(
            """
            () => {
                try {
                    if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
                        let t = null;
                        try { t = window.turnstile.getResponse(); } catch (e) {}
                        if (t && t.length > 30) return t;
                        for (let i = 0; i < 5; i++) {
                            try { t = window.turnstile.getResponse(String(i)); } catch (e) { t = null; }
                            if (t && t.length > 30) return t;
                        }
                    }
                } catch (e) {}
                const inputs = document.querySelectorAll(
                    'input[name="cf-turnstile-response"], input[id$="_response"]'
                );
                for (const el of inputs) {
                    if (el.value && el.value.length > 30) return el.value;
                }
                return null;
            }
            """
        )
    except Exception:
        return None

def _find_visible_cf_frames(page):
    result = []
    try:
        for handle in page.query_selector_all(CF_IFRAME_SELECTOR):
            try:
                box = handle.bounding_box()
                if box and box['width'] > 10 and box['height'] > 10:
                    result.append(handle)
            except Exception:
                continue
    except Exception:
        pass
    return result

def _cf_checkbox_visible(page):
    for frame in page.frames:
        if 'challenges.cloudflare.com' not in (frame.url or ''):
            continue
        try:
            if frame.locator('input[type="checkbox"]:visible').count() > 0:
                return True
        except Exception:
            continue
    return False

def _click_cf_checkbox(page, frame_el=None):
    for frame in page.frames:
        if 'challenges.cloudflare.com' not in (frame.url or ''):
            continue
        try:
            frame.locator('input[type="checkbox"]').first.click(timeout=2500)
            return True
        except Exception:
            continue
    if frame_el is None:
        return False
    try:
        try:
            frame_el.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        box = frame_el.bounding_box()
        if not box:
            return False
        x = box['x'] + random.uniform(18, 34)
        y = box['y'] + box['height'] / 2 + random.uniform(-4, 4)
        page.mouse.move(x - random.uniform(30, 60), y + random.uniform(-8, 8))
        time.sleep(random.uniform(0.15, 0.4))
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.05, 0.2))
        page.mouse.down()
        time.sleep(random.uniform(0.04, 0.1))
        page.mouse.up()
        return True
    except Exception:
        return False

SECURITY_TITLE_HINTS = ('security verification', 'just a moment', 'attention required', 'checking your browser', '请稍候', 'please wait', 'one more step')

def _is_security_check_page(page):
    try:
        title = (page.title() or '').lower()
        if any(h in title for h in SECURITY_TITLE_HINTS):
            return True
    except Exception:
        return True
    try:
        return page.evaluate(
            """
            () => {
                const t = document.body ? document.body.innerText.slice(0, 5000).toLowerCase() : '';
                return t.includes('verify you are human') || t.includes('checking your browser')
                    || t.includes('security verification');
            }
            """
        )
    except Exception:
        return True

def _has_interstitial_iframe(page):
    try:
        for handle in page.query_selector_all(CF_IFRAME_SELECTOR):
            if '/turnstile/' not in (handle.get_attribute('src') or ''):
                return True
    except Exception:
        pass
    return False

def _click_security_submit(page):
    for text in ('Verify', 'Continue', 'Submit', 'Proceed', '验证'):
        try:
            btn = page.locator(f'button:has-text("{text}"):visible, input[type="submit"]:visible').first
            if btn.count() > 0:
                btn.click(timeout=3000)
                log(f"🖱️ 已点击安全验证页的确认按钮（{text}）...")
                return True
        except Exception:
            continue
    return False

def _dump_security_page(page):
    try:
        page.screenshot(path="security_page.png")
    except Exception:
        pass

def handle_cloudflare(page, timeout=240):
    def challenge_active():
        return _has_interstitial_iframe(page) or _is_security_check_page(page)

    if not challenge_active():
        for _ in range(3):
            time.sleep(1)
            if challenge_active():
                break
        else:
            return True

    log("🔒 检测到 Cloudflare 安全验证...")
    time.sleep(5)
    _dump_security_page(page)

    effective_timeout = timeout + (180 if timeout > 60 else 0)
    manual_hinted = False
    start_time = time.time()
    last_click = 0
    clear_rounds = 0
    while time.time() - start_time < effective_timeout:
        if not challenge_active():
            clear_rounds += 1
            if clear_rounds >= 2: 
                return True
            time.sleep(1)
            continue
        clear_rounds = 0
        if not manual_hinted and timeout > 60 and time.time() - start_time > timeout - 30:
            log("🤝 自动点击未能通过验证，脚本会继续等待...")
            manual_hinted = True
        if time.time() - last_click > 6:
            frames = _find_visible_cf_frames(page)
            if frames:
                log("🖱️ 点击 Turnstile 验证......")
                if _click_cf_checkbox(page, frames[-1]):
                    last_click = time.time()
                    time.sleep(random.uniform(3, 5))
                    continue
            elif _get_turnstile_token(page) and _is_security_check_page(page):
                if _click_security_submit(page):
                    last_click = time.time()
                    time.sleep(random.uniform(2, 4))
                    continue
        time.sleep(1)
    log("❌ 验证超时。")
    return False

def solve_modal_turnstile(page, timeout=90):
    log("🛡️ 开始处理 Turnstile 验证...")
    start = time.time()
    last_click = 0
    clicks = 0
    no_frame_seconds = 0
    while time.time() - start < timeout:
        if _get_turnstile_token(page):
            log("✅ Turnstile 验证通过！")
            return True
        frames = _find_visible_cf_frames(page)
        if not frames:
            no_frame_seconds += 1
            if no_frame_seconds >= 20 and clicks == 0:
                log("ℹ️ 未检测到 Turnstile 验证框，无需验证。")
                return True
            time.sleep(1)
            continue
        no_frame_seconds = 0
        if clicks > 0 and time.time() - last_click > 4 and not _cf_checkbox_visible(page):
            time.sleep(2)
            if not _cf_checkbox_visible(page):
                log("✅ Turnstile 复选框已消失，视为验证通过！")
                return True
        if time.time() - last_click > 6 and _cf_checkbox_visible(page):
            log(f"🖱️ 点击 Turnstile 复选框（第 {clicks + 1} 次）...")
            if _click_cf_checkbox(page, frames[-1]):
                clicks += 1
                last_click = time.time()
                time.sleep(random.uniform(3, 5))
                continue
        if clicks == 0 and time.time() - start > 20 and time.time() - last_click > 6:
            if _click_cf_checkbox(page, frames[-1]):
                clicks += 1
                last_click = time.time()
                time.sleep(random.uniform(3, 5))
                continue
        time.sleep(1)
    if _get_turnstile_token(page):
        log("✅ Turnstile 验证通过！")
        return True
    log("❌ Turnstile 验证超时。")
    return False

def open_browser(p):
    proxy_arg = {"server": PROXY_SERVER} if IS_PROXY else None
    if USING_PATCHRIGHT:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=['--disable-infobars'],
            proxy=proxy_arg,
        )
        ctx = browser.new_context(viewport=None, proxy=proxy_arg)
        page = ctx.new_page()
        return browser, page
    log("⚠️ 未安装 patchright，退回原生 playwright，过 Cloudflare 能力较弱")
    browser = p.chromium.launch(
        channel="chrome",
        headless=False,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-infobars']
    )
    ctx = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent=DEFAULT_UA,
        proxy=proxy_arg,
    )
    page = ctx.new_page()
    page.add_init_script(STEALTH_JS)
    return browser, page

def _is_logged_in(page):
    try:
        url = page.url or ''
        if 'dash.hidencloud.com' not in url:
            return False
        if 'auth/login' in url or _is_security_check_page(page):
            return False
        return True
    except Exception:
        return False

def login(page):
    if COOKIE_VALUE:
        log("📇 尝试 Cookie 登录...")
        try:
            page.context.add_cookies([{
                'name': 'remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d',
                'value': COOKIE_VALUE,
                'domain': 'dash.hidencloud.com',
                'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
                'httpOnly': True,
                'secure': True,
                'sameSite': 'Lax'
            }])
            page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
            handle_cloudflare(page, timeout=240)
            time.sleep(2)
            handle_cloudflare(page, timeout=60)
            if _is_logged_in(page):
                log(f"✅ Cookie 登录成功！当前已到达dashboard页面")
                return True
            log("❌ Cookie 失效，请更换")
        except Exception as e:
            log(f"⚠️ Cookie 登录尝试异常: {e}")

    if not EMAIL or not PASSWORD:
        return False
    log("💣 尝试账号密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page, timeout=240)
        time.sleep(8)
        log("⌨️ 输入账号密码...")
        user_input = page.locator('input[name="username"], input[name="email"], input[type="email"]').first
        pwd_input = page.locator('input[name="password"], input[type="password"]').first
        try:
            user_input.wait_for(state="visible", timeout=30000)
        except Exception:
            handle_cloudflare(page, timeout=120)
            user_input.wait_for(state="visible", timeout=30000)
        user_input.fill(EMAIL, timeout=10000)
        pwd_input.fill(PASSWORD, timeout=10000)
        time.sleep(0.5)
        handle_cloudflare(page, timeout=60)
        
        if not solve_modal_turnstile(page, timeout=90):
            log("⚠️ 登录表单的 Turnstile 未确认通过，仍将尝试提交...")
        
        log("🖱️ 点击登录按钮提交...")
        time.sleep(3)
        try:
            page.click('button[type="submit"]', timeout=10000)
        except Exception:
            page.locator('button:has-text("Sign in"), button:has-text("登录")').first.click(timeout=10000)
        time.sleep(3)
        handle_cloudflare(page, timeout=240)
        nav_start = time.time()
        navigated = False
        while time.time() - nav_start < 120:
            try:
                if "/auth/login" not in page.url and not _is_security_check_page(page):
                    navigated = True
                    break
                if _is_security_check_page(page) or _has_interstitial_iframe(page):
                    handle_cloudflare(page, timeout=60)
            except Exception:
                pass
            time.sleep(1)
        if not navigated:
            log("❌ 登录提交后未能完成跳转。")
            return False
        page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page, timeout=120)
        page_title = page.title()
        log(f"📝 当前Title: {page_title}")
        if not _is_logged_in(page):
            log("❌ 登录失败。")
            return False
        log(f"✅ 账号密码登录成功！当前已到达dashboard页面")
        return True
    except Exception as e:
        log(f"❌ 登录异常: {e}")
        return False

def get_server_id(page):
    try:
        if 'dash.hidencloud.com' not in page.url:
            log("⚠️ 当前不在控制台页面，先跳转 dashboard...")
            page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
            handle_cloudflare(page)
            time.sleep(2)
        handle_cloudflare(page)
        time.sleep(3)
        html = page.content()

        matches = re.findall(r'/service/(\d+)/manage', html)
        if matches:
            return matches[0]

        matches = [m for m in re.findall(r'#(\d{4,})', html) if set(m) != {'0'}]
        if matches:
            return matches[0]

        log("❌ 所有 URL 均未找到 Server ID")
        return None
    except Exception as e:
        log(f"❌ 获取 Server ID 失败: {e}")
        return None

def get_due_date(page):
    try:
        if SERVICE_URL not in page.url:
            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        body_text = page.locator("body").inner_text()
        patterns = [
            r"Due date\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
            r"Due date\s*\n\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
            r"Due date.*?(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
    except Exception as e:
        log(f"❌ 获取Due Date失败: {e}")
    return "未知"

def renew_service(page):
    try:
        log("➡ 进入续期流程...")
        if page.url != SERVICE_URL:
            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        time.sleep(12) 
        log("🖱️ 准备点击 Renew 按钮...")
        renew_btn = page.locator('button:has-text("Renew")')
        create_btn = page.locator('button:has-text("Create Invoice")')
        modal_opened = False
        for i in range(6):
            try:
                renew_btn.wait_for(state="visible", timeout=10000)
                renew_btn.scroll_into_view_if_needed()
                log(f"🖱️ 第 {i+1} 次尝试点击 Renew...")
                renew_btn.click()
                time.sleep(3) 
                page_text = page.locator("body").inner_text()
                if "Renewal Restricted" in page_text or "can only renew" in page_text.lower():
                    log("⚠️ 未到续期时间，无法续期。")
                    return "NOT_TIME" 

                log("🖲️ 等待弹窗出现...")
                try:
                    create_btn.wait_for(state="visible", timeout=8000)
                    modal_opened = True
                    log("✅ 弹窗已成功弹出！")
                    break
                except:
                    log("⚠️ 弹窗未出现，可能是点击未响应，准备重试...")
                    time.sleep(2)
            except Exception as e:
                pass

        if not modal_opened:
            log("❌ 错误：尝试多次后，续费弹窗仍未出现。")
            return False

        handle_cloudflare(page, timeout=60)
        if not solve_modal_turnstile(page, timeout=90):
            log("⚠️ Turnstile 未确认通过，仍将尝试提交...")

        new_invoice_url = None
        time.sleep(2)
        for attempt in range(6):
            log(f"🖱️ 点击 Create Invoice（第 {attempt + 1} 次）...")
            try:
                create_btn.wait_for(state="visible", timeout=30000)
                create_btn.click(timeout=20000)
            except Exception as e:
                log(f"⚠️ 点击 Create Invoice 失败: {e}")
                solve_modal_turnstile(page, timeout=45)
                time.sleep(2)
                continue

            start_wait = time.time()
            while time.time() - start_wait < 30:
                if "/payment/invoice/" in page.url:
                    new_invoice_url = page.url
                    log(f"🎉 页面已跳转: {new_invoice_url}")
                    break
                if _has_interstitial_iframe(page) or _is_security_check_page(page):
                    log("⚠️ 遇到整页拦截，尝试处理...")
                    handle_cloudflare(page, timeout=60)
                time.sleep(1)
            if new_invoice_url:
                break

            log("⚠️ 未跳转到发票页面，尝试重新完成 Turnstile 验证后重试...")
            solve_modal_turnstile(page, timeout=45)

        if not new_invoice_url:
            log("❌ 未能进入发票页面，超时。")
            return False

        if page.url != new_invoice_url:
            page.goto(new_invoice_url)
        handle_cloudflare(page)

        log("🔎 查找 Pay 按钮...")
        pay_btn = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_btn.wait_for(state="visible", timeout=30000)
        pay_btn.click()
        log("✅ Pay 按钮已点击")
        time.sleep(6) 
        page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000) 
        handle_cloudflare(page)
        return True

    except Exception as e:
        log(f"❌ 续费异常: {e}")
        return False

def main():
    log("=== 启动 HidenCloud 自动化续期任务 ===")
    if not COOKIE_VALUE and not (EMAIL and PASSWORD):
        log("❌ 致命错误：缺少登录凭证")
        sys.exit(1)

    global SERVICE_URL

    with sync_playwright() as p:
        browser = None
        try:
            current_ip = get_current_ip(PROXY_SERVER)
            log(f"🎯 当前出口IP: {current_ip}")

            log("🚀 启动反检测内核浏览器...") 
            browser, page = open_browser(p)

            if not login(page):
                sys.exit(1)

            server_id = get_server_id(page)
            if not server_id:
                log("❌ 无法获取 Server ID，退出。")
                sys.exit(1)
            SERVICE_URL = f"{BASE_URL}/service/{server_id}/manage"

            old_due = get_due_date(page)
            log(f"📆 续费前到期时间：{old_due}")

            renew_result = renew_service(page)

            new_due = old_due
            if renew_result == "NOT_TIME":
                status = "⏳ 未到续期时间"
            elif renew_result is False:
                status = "❌ 续期失败"
            else:
                new_due = get_due_date(page)
                status = "✅ 续期成功"

            log(f"📢 准备发送通知 -> 状态: {status} | 旧到期: {old_due} | 新到期: {new_due}")
            send_telegram_notification(status, old_due, new_due, current_ip)
            send_wechat_notification(status, old_due, new_due, current_ip)

            if renew_result == "NOT_TIME":
                sys.exit(0)
            elif renew_result is False:
                sys.exit(1)
            else:
                sys.exit(0)
        except Exception as e:
            sys.exit(1)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
                
if __name__ == "__main__":
    main()
