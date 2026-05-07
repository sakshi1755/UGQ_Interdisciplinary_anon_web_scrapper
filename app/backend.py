"""
VisualScrape Backend
====================
Uses Chrome profile (logged in, cookies, not headless)
so sites like Reddit/YouTube don't block the scraper.
headless=False → Chrome opens visibly → looks like a real user → harder to detect as bot
headless=True  → no window → easily fingerprinted → gets blocked
Run: python backend.py
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from playwright.sync_api import sync_playwright
import base64, time, os, shutil, tempfile, atexit, random
import subprocess
import requests
import imageio_ffmpeg
import speech_recognition as sr
app = Flask(__name__)
CORS(app)
CHROME_PROFILE = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data\Default")
TMP_DIRS = []
def cleanup_tmp():
    for d in TMP_DIRS:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
atexit.register(cleanup_tmp)
def get_page(playwright):
    tmp_dir = tempfile.mkdtemp(prefix="pw_chrome_")
    TMP_DIRS.append(tmp_dir)
    tmp_profile = os.path.join(tmp_dir, "Default")
    os.makedirs(tmp_profile, exist_ok=True)
    for item in ["Cookies", "Local Storage", "Session Storage", "Preferences"]:
        src = os.path.join(CHROME_PROFILE, item)
        dst = os.path.join(tmp_profile, item)
        try:
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst)
        except Exception as e:
            print(f"[profile] Could not copy '{item}': {e}")
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=tmp_dir,
        channel="chrome",
        headless=False,          
        args=["--profile-directory=Default"],
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()
    return context, page
def scroll_human(page, scrolls=6):
    for i in range(scrolls):
        distance = random.randint(400, 900)
        page.mouse.wheel(0, distance)
        time.sleep(random.uniform(0.8, 2.0))
    print(f"[scroll] Done ({scrolls} steps)")
def solve_recaptcha_with_buster(page):
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        audio_path = "captcha.mp3"
        wav_path   = "captcha.wav"
        print("[captcha] Looking for CAPTCHA...")
        page.wait_for_timeout(2000)
        recaptcha_frame = page.frame_locator("iframe[title='reCAPTCHA']")
        checkbox = recaptcha_frame.locator("#recaptcha-anchor")
        try:
            checkbox.wait_for(timeout=5000)
        except Exception:
            print("[captcha] No CAPTCHA checkbox found (or wait timed out).")
            return
        checkbox.click()
        print("[captcha] Clicked the checkbox")
        page.wait_for_timeout(3000)
        challenge_frame = page.frame_locator("iframe[title='recaptcha challenge expires in two minutes']")
        try:
            audio_btn = challenge_frame.locator("#recaptcha-audio-button")
            audio_btn.wait_for(timeout=5000)
            audio_btn.click()
        except Exception:
            print("[captcha] No audio button found or CAPTCHA solved without challenge.")
            return
        print("[captcha] Clicked audio button...")
        page.wait_for_timeout(2000)
        audio_link = challenge_frame.locator(".rc-audiochallenge-tdownload-link")
        audio_url = audio_link.get_attribute("href")
        if not audio_url:
            print("[captcha] No audio URL found.")
            return
        print(f"[captcha] Got audio URL: {audio_url[:60]}...")
        r = requests.get(audio_url)
        with open(audio_path, "wb") as f:
            f.write(r.content)
        print(f"[captcha] Downloaded audio -> {audio_path}")
        result = subprocess.run(
            [ffmpeg_exe, "-y", "-i", audio_path, wav_path],
            capture_output=True,
            text=True
        )
        if not os.path.exists(wav_path):
            print("[captcha] ffmpeg failed. Error:", result.stderr)
            return
        print(f"[captcha] Converted to WAV -> {wav_path}")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data)
            print(f"[captcha] Heard: '{text}'")
        except sr.UnknownValueError:
            print("[captcha] Speech Recognition could not understand audio")
            return
        except sr.RequestError as e:
            print(f"[captcha] Could not request results from Google SR service; {e}")
            return
        answer_field = challenge_frame.locator("#audio-response")
        answer_field.fill(text.lower())
        print("[captcha] Typed the answer...")
        verify_btn = challenge_frame.locator("#recaptcha-verify-button")
        verify_btn.click()
        print("[captcha] Submitted! CAPTCHA should be solved!")
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"[captcha] Error solving captcha: {e}")
def load_page_properly(page, url):
    print(f"[load] First load: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    time.sleep(5)
    print(f"[load] Checking for captcha instead of reloading...")
    solve_recaptcha_with_buster(page)
    scroll_human(page)
    time.sleep(3)
    print(f"[load] Page ready.")
CONTENT_MARKERS = [
    'ytd-video-renderer', 'ytd-rich-item-renderer', 'ytd-compact-video-renderer',
    'shreddit-post', 'data-testid="post-', '[data-testid="post-container"]',
    '<article', '<li class="', 'class="post ', 'class="item ', 'class="card ',
    'class="product', 'class="result', 'class="listing', 'class="entry',
    'class="product-item', 'class="product-card', 'data-product',
    'class="story', 'class="article', 'class="news-item',
]
def extract_content_html(html, max_chars=15000):
    lower = html.lower()
    for marker in CONTENT_MARKERS:
        idx = lower.find(marker.lower())
        if idx != -1:
            start = max(0, idx - 300)
            chunk = html[start: start + max_chars]
            print(f"[extract] Found marker '{marker}' at pos {idx}, returning chunk from {start}")
            return chunk
    body_start = lower.find('<body')
    if body_start != -1:
        print(f"[extract] No marker found, using <body> at pos {body_start}")
        return html[body_start: body_start + max_chars]
    mid = int(len(html) * 0.3)
    print(f"[extract] No <body> found, using 30% offset at pos {mid}")
    return html[mid: mid + max_chars]
@app.route("/fetch-page", methods=["POST"])
def fetch_page():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    print(f"\n[fetch-page] {url}")
    try:
        with sync_playwright() as p:
            context, page = get_page(p)
            load_page_properly(page, url)
            html = page.content()
            screenshot = page.screenshot(full_page=False)
            context.close()
        screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
        print(f"[fetch-page] Done — {len(html)} chars HTML")
        return jsonify({"html": html, "screenshot": screenshot_b64})
    except Exception as e:
        print(f"[fetch-page] ERROR: {e}")
        return jsonify({"error": str(e)}), 500
@app.route("/inspect-first-container", methods=["POST"])
def inspect_first_container():
    url = request.json.get("url", "").strip()
    hint_selector = request.json.get("hint_selector", "article")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    print(f"\n[inspect-first-container] {url}")
    try:
        with sync_playwright() as p:
            context, page = get_page(p)
            load_page_properly(page, url)
            result = page.evaluate("""
                (hintSelector) => {
                    const selectors = hintSelector.split(',').map(s => s.trim());
                    let containers = [];
                    let usedSelector = '';
                    for (const sel of selectors) {
                        try {
                            const found = document.querySelectorAll(sel);
                            if (found.length > 2) {
                                containers = Array.from(found).slice(0, 3);
                                usedSelector = sel;
                                break;
                            }
                        } catch(e) {}
                    }
                    if (containers.length === 0) return { context: '', selector: '' };
                    const describeEl = (el, depth) => {
                        depth = depth || 0;
                        if (depth > 2) return null;
                        const attrs = {};
                        for (const a of el.attributes) {
                            attrs[a.name] = a.value.substring(0, 120);
                        }
                        const extraProps = {};
                        const propNames = [
                            'score', 'count', 'value', 'label', 'text', 'href', 'src',
                            'vote', 'votes', 'karma', 'points', 'comments', 'commentCount',
                            'title', 'author', 'username', 'name', 'rating', 'price',
                            'views', 'likes', 'shares', 'time', 'date', 'timestamp'
                        ];
                        for (const prop of propNames) {
                            try {
                                if (el[prop] !== undefined && el[prop] !== null && el[prop] !== '') {
                                    extraProps[prop] = String(el[prop]).substring(0, 120);
                                }
                            } catch(e) {}
                        }
                        const children = Array.from(el.children).slice(0, 25).map(c => {
                            const childAttrs = {};
                            for (const a of c.attributes) {
                                childAttrs[a.name] = a.value.substring(0, 80);
                            }
                            const childProps = {};
                            for (const prop of propNames) {
                                try {
                                    if (c[prop] !== undefined && c[prop] !== null && c[prop] !== '') {
                                        childProps[prop] = String(c[prop]).substring(0, 80);
                                    }
                                } catch(e) {}
                            }
                            const grandchildren = Array.from(c.children).slice(0, 10).map(gc => ({
                                tag: gc.tagName.toLowerCase(),
                                attrs: Array.from(gc.attributes).reduce((acc, a) => { acc[a.name] = a.value.substring(0, 60); return acc; }, {}),
                                text: gc.innerText?.trim().substring(0, 80)
                            }));
                            return {
                                tag: c.tagName.toLowerCase(),
                                attrs: childAttrs,
                                props: childProps,
                                innerText: c.innerText?.trim().substring(0, 100),
                                children: grandchildren
                            };
                        }).filter(Boolean);
                        return {
                            tag: el.tagName.toLowerCase(),
                            attrs,
                            props: extraProps,
                            innerText: el.innerText?.trim().substring(0, 200),
                            children
                        };
                    };
                    const descriptions = containers.map(c => describeEl(c));
                    const lines = [];
                    lines.push(`Container selector used: ${usedSelector}`);
                    lines.push(`Found ${containers.length} containers. First 3 inspected:\\n`);
                    descriptions.forEach((desc, i) => {
                        if (!desc) return;
                        lines.push(`--- Container ${i+1} ---`);
                        lines.push(`Tag: <${desc.tag}>`);
                        lines.push(`Attributes: ${JSON.stringify(desc.attrs)}`);
                        if (Object.keys(desc.props).length > 0) {
                            lines.push(`JS Properties: ${JSON.stringify(desc.props)}`);
                        }
                        lines.push(`Children (${desc.children.length}):`);
                        desc.children.forEach(child => {
                            const attrStr = JSON.stringify(child.attrs);
                            const propStr = Object.keys(child.props).length > 0 ? ` props=${JSON.stringify(child.props)}` : '';
                            const gcStr = child.children && child.children.length > 0
                                ? ` grandchildren=[${child.children.map(gc => `<${gc.tag} ${JSON.stringify(gc.attrs)} "${gc.text}"`).join(', ')}]`
                                : '';
                            lines.push(`  <${child.tag}> attrs=${attrStr}${propStr} text="${child.innerText}"${gcStr}`);
                        });
                        lines.push('');
                    });
                    return { context: lines.join('\\n'), selector: usedSelector };
                }
            """, hint_selector)
            context.close()
        print(f"[inspect-first-container] Done — {len(result.get('context', ''))} chars")
        return jsonify(result)
    except Exception as e:
        print(f"[inspect-first-container] ERROR: {e}")
        return jsonify({"error": str(e)}), 500
@app.route("/scrape", methods=["POST"])
def scrape():
    data      = request.json
    url       = data.get("url", "").strip()
    container = data.get("container_selector", "")
    fields    = data.get("fields", {})
    count     = int(data.get("item_count", 10))
    if not url or not container:
        return jsonify({"error": "url and container_selector are required"}), 400
    fields = {k: v for k, v in fields.items() if v and v not in ("null", "none", "undefined")}
    print(f"\n[scrape] container={container} fields={list(fields.keys())} count={count}")
    try:
        with sync_playwright() as p:
            context, page = get_page(p)
            load_page_properly(page, url)
            rendered_html = page.content()
            print(f"[scrape] Rendered HTML: {len(rendered_html)} chars")
            try:
                found_count = page.evaluate(
                    f"() => document.querySelectorAll({repr(container)}).length"
                )
                print(f"[scrape] Containers found: {found_count}")
            except Exception as e:
                found_count = 0
                print(f"[scrape] Count error: {e}")
            items = page.evaluate(
                """
                (params) => {
                    const { container, fields, count } = params;
                    const containers = Array.from(
                        document.querySelectorAll(container)
                    ).slice(0, count);
                    function extractValue(el, selector, fieldName) {
                        if (!selector || selector === 'null') return '';
                        if (selector.startsWith('attribute::')) {
                            const attr = selector.replace('attribute::', '');
                            return el.getAttribute(attr) || '';
                        }
                        if (selector.includes('::')) {
                            const parts = selector.split('::');
                            const elemSel = parts[0].trim();
                            const attrName = parts[1].trim();
                            try {
                                const found = el.querySelector(elemSel);
                                if (found) {
                                    const attrVal = found.getAttribute(attrName);
                                    if (attrVal !== null && attrVal !== '') return attrVal;
                                    const dataVal = found.getAttribute('data-' + attrName);
                                    if (dataVal !== null && dataVal !== '') return dataVal;
                                    if (found[attrName] !== undefined && found[attrName] !== null && found[attrName] !== '') {
                                        return String(found[attrName]);
                                    }
                                    const text = found.innerText?.trim();
                                    if (text) return text;
                                }
                                const shadow = el.shadowRoot;
                                if (shadow) {
                                    const shadowFound = shadow.querySelector(elemSel);
                                    if (shadowFound) {
                                        const sv = shadowFound.getAttribute(attrName) || shadowFound[attrName];
                                        if (sv !== null && sv !== undefined && sv !== '') return String(sv);
                                        return shadowFound.innerText?.trim() || '';
                                    }
                                }
                            } catch(e) {}
                            return '';
                        }
                        if (selector === 'self' || selector === ':scope') {
                            return el.innerText?.replace(/\s+/g, ' ').trim().substring(0, 400) || '';
                        }
                        try {
                            let found = el.querySelector(selector);
                            if (!found && el.shadowRoot) {
                                found = el.shadowRoot.querySelector(selector);
                            }
                            if (found) {
                                if (found.tagName === 'A' && fieldName.toLowerCase().includes('url')) {
                                    return found.href || found.getAttribute('href') || found.innerText.trim();
                                }
                                if (found.tagName === 'A') {
                                    const text = found.innerText?.replace(/\s+/g, ' ').trim();
                                    return text || found.getAttribute('aria-label') || found.getAttribute('title') || '';
                                }
                                return (
                                    found.innerText?.replace(/\s+/g, ' ').trim() ||
                                    found.getAttribute('aria-label') ||
                                    found.getAttribute('title') ||
                                    ''
                                ).substring(0, 400);
                            }
                        } catch(e) {}
                        const fieldKey = fieldName.toLowerCase().replace(/[\s_\-]/g, '');
                        for (const attr of el.attributes) {
                            const attrKey = attr.name.toLowerCase().replace(/[\-_]/g, '');
                            if (
                                (attrKey.includes(fieldKey) || fieldKey.includes(attrKey)) &&
                                attrKey.length > 1 &&
                                attr.value.length > 0
                            ) {
                                return attr.value.substring(0, 400);
                            }
                        }
                        return '';
                    }
                    return containers.map(el => {
                        const item = {};
                        for (const [fieldName, selector] of Object.entries(fields)) {
                            item[fieldName] = extractValue(el, selector, fieldName);
                        }
                        return item;
                    }).filter(item => Object.values(item).some(v => v !== ''));
                }
                """,
                {"container": container, "fields": fields, "count": count}
            )
            context.close()
        content_html = extract_content_html(rendered_html, max_chars=60000)
        print(f"[scrape] Extracted {len(items)} items")
        return jsonify({
            "items": items,
            "count": len(items),
            "containers_found": found_count,
            "rendered_html": content_html,
        })
    except Exception as e:
        print(f"[scrape] ERROR: {e}")
        return jsonify({"error": str(e)}), 500
@app.route("/debug-html", methods=["POST"])
def debug_html():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    print(f"\n[debug-html] {url}")
    try:
        with sync_playwright() as p:
            context, page = get_page(p)
            load_page_properly(page, url)
            html = page.content()
            context.close()
        content_html = extract_content_html(html, max_chars=100000)
        print(f"[debug-html] Done — {len(content_html)} chars content HTML")
        return jsonify({"html": content_html, "total_length": len(html)})
    except Exception as e:
        print(f"[debug-html] ERROR: {e}")
        return jsonify({"error": str(e)}), 500
@app.route("/screenshot", methods=["POST"])
def screenshot():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    print(f"\n[screenshot] {url}")
    try:
        with sync_playwright() as p:
            context, page = get_page(p)
            load_page_properly(page, url)
            shot = page.screenshot(full_page=False)
            context.close()
        shot_b64 = base64.b64encode(shot).decode("utf-8")
        print(f"[screenshot] Done")
        return jsonify({"screenshot": shot_b64})
    except Exception as e:
        print(f"[screenshot] ERROR: {e}")
        return jsonify({"error": str(e)}), 500
@app.route("/inspect-element", methods=["POST"])
def inspect_element():
    url      = request.json.get("url", "").strip()
    selector = request.json.get("selector", "").strip()
    if not url or not selector:
        return jsonify({"error": "url and selector required"}), 400
    print(f"\n[inspect] '{selector}' on {url}")
    try:
        with sync_playwright() as p:
            context, page = get_page(p)
            load_page_properly(page, url)
            info = page.evaluate("""
                (sel) => {
                    const elements = Array.from(document.querySelectorAll(sel)).slice(0, 3);
                    if (elements.length === 0) return { found: false, selector: sel };
                    return elements.map(el => {
                        const attrs = {};
                        for (const a of el.attributes) attrs[a.name] = a.value.substring(0, 300);
                        const children = Array.from(el.children).map(c => ({
                            tag: c.tagName.toLowerCase(),
                            attrs: Array.from(c.attributes).reduce((acc, a) => { acc[a.name] = a.value.substring(0, 100); return acc; }, {}),
                            text: c.innerText?.substring(0, 100)
                        }));
                        return {
                            found: true,
                            tagName: el.tagName.toLowerCase(),
                            attributes: attrs,
                            innerText: el.innerText?.substring(0, 300),
                            children: children.slice(0, 15)
                        };
                    });
                }
            """, selector)
            context.close()
        print(f"[inspect] Done")
        return jsonify({"results": info})
    except Exception as e:
        print(f"[inspect] ERROR: {e}")
        return jsonify({"error": str(e)}), 500
if __name__ == "__main__":
    print("=" * 55)
    print("  VisualScrape backend  →  http://localhost:5000")
    print(f"  Chrome profile: {CHROME_PROFILE}")
    print("  Routes:")
    print("    POST /fetch-page              — load URL, HTML + screenshot")
    print("    POST /scrape                  — extract items with CSS selectors")
    print("    POST /inspect-first-container — auto-detect element attrs for AI")
    print("    POST /debug-html              — rendered content HTML for debugging")
    print("    POST /screenshot              — fresh screenshot of a URL")
    print("    POST /inspect-element         — inspect element attrs & children")
    print("=" * 55)
    app.run(port=5000, debug=False)