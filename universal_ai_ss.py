"""
🌐 Universal AI-Powered Scraper (Two-Phase Discovery)
======================================================
Phase 1: Gemini analyzes the LISTING page  → finds post containers, titles, URLs
Phase 2: Gemini analyzes a real POST PAGE  → finds body text, comments selectors
Then visits every post and extracts real content.

Works on Reddit, Twitter/X, HackerNews, any site.
No hardcoded selectors — 100% AI-driven discovery.
"""

import pandas as pd
from playwright.sync_api import sync_playwright
import json
import re
import time
from google import genai
from PIL import Image
import io
from datetime import datetime

import os
from dotenv import load_dotenv

load_dotenv()

class UniversalScraper:
    def __init__(self, api_key: str, model="gemini-2.5-flash"):
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def get_listing_snapshot(self, page) -> str:
        return page.evaluate("""
            () => {
                const candidates = [
                    ...document.querySelectorAll('article'),
                    ...document.querySelectorAll('[data-testid]'),
                    ...document.querySelectorAll('shreddit-post'),
                    ...document.querySelectorAll('[class*="post"]'),
                    ...document.querySelectorAll('[class*="tweet"]'),
                    ...document.querySelectorAll('[class*="card"]'),
                    ...document.querySelectorAll('li'),
                ];
                const unique = [...new Set(candidates)].slice(0, 8);
                return JSON.stringify(unique.map(el => {
                    const attrs = {};
                    for (let a of el.attributes) attrs[a.name] = a.value;
                    return {
                        tag: el.tagName,
                        attrs,
                        text: el.innerText?.replace(/\\s+/g, ' ').substring(0, 150)
                    };
                }));
            }
        """)

    def get_detail_snapshot(self, page) -> str:
        return page.evaluate("""
            () => {
                const candidates = [
                    ...document.querySelectorAll('[class*="comment"]'),
                    ...document.querySelectorAll('[data-testid]'),
                    ...document.querySelectorAll('shreddit-comment'),
                    ...document.querySelectorAll('[class*="body"]'),
                    ...document.querySelectorAll('[class*="content"]'),
                    ...document.querySelectorAll('article'),
                    ...document.querySelectorAll('p'),
                ];
                const unique = [...new Set(candidates)].slice(0, 10);
                return JSON.stringify(unique.map(el => {
                    const attrs = {};
                    for (let a of el.attributes) attrs[a.name] = a.value;
                    return {
                        tag: el.tagName,
                        attrs,
                        text: el.innerText?.replace(/\\s+/g, ' ').substring(0, 150)
                    };
                }));
            }
        """)
    
    def discover_listing_structure(self, screenshot_path: str, html_map: str, site_url: str) -> dict | None:
        with open(screenshot_path, "rb") as f:
            image = Image.open(io.BytesIO(f.read()))

        prompt = f"""
You are an expert web scraping assistant analyzing the LISTING/FEED page of: {site_url}

HTML sample of elements on the page:
{html_map}

Look at BOTH the screenshot and HTML carefully.
Your job: figure out how to extract each post/tweet/article from this listing page.

Return ONLY a valid JSON object — no markdown, no explanation:
{{
    "site_type": "reddit | twitter | news | forum | other",
    "container_selector": "CSS selector for each post/tweet container",
    "fields": {{
        "title": "CSS selector or attribute name for post title or tweet text",
        "url": "CSS selector or attribute name for the link to the full post",
        "author": "CSS selector or attribute name for the author/username",
        "score": "CSS selector or attribute name for likes/upvotes (or null)",
        "timestamp": "CSS selector or attribute name for the time (or null)"
    }},
    "notes": "anything special like infinite scroll, login walls, etc."
}}

RULES:
- For Reddit: container is article[data-post-id], use 'data-post-id' for the url field, use 'aria-label' for title
- For Twitter/X: container is article[data-testid="tweet"], use div[data-testid="tweetText"] for title
- CSS selectors in 'fields' are queried INSIDE each container element
- Return null for any field you cannot confidently find
- Only return the JSON object, nothing else
"""
        return self._call_gemini(prompt, image, "listing")


    def discover_detail_structure(self, screenshot_path: str, html_map: str, site_url: str) -> dict | None:
        with open(screenshot_path, "rb") as f:
            image = Image.open(io.BytesIO(f.read()))

        prompt = f"""
You are an expert web scraping assistant analyzing a POST DETAIL PAGE from: {site_url}

This is a single post/tweet page — NOT the feed/listing.

HTML sample of elements on the page:
{html_map}

Look at BOTH the screenshot and HTML very carefully.
The screenshot shows the actual rendered page — use it to confirm what you see in the HTML.

Your job: find the exact CSS selectors for the post body and comments.

Return ONLY a valid JSON object — no markdown, no explanation:
{{
    "body_selector": "CSS selector for the main post body text",
    "single_comment_selector": "CSS selector for each individual comment element",
    "comment_author_selector": "CSS selector for comment author (scoped inside each comment)",
    "comment_text_selector": "CSS selector for comment text (scoped inside each comment)",
    "comment_score_selector": "CSS selector for comment score/likes (or null)",
    "notes": "anything special about how comments load"
}}

RULES:
- Be very specific — use tag + attribute combos like div[slot='comment'] or shreddit-comment
- The comment selectors (author, text, score) are scoped INSIDE each single_comment_selector element
- If you cannot find something, return null for that field
- Only return the JSON object, nothing else
"""
        return self._call_gemini(prompt, image, "detail")

    def _call_gemini(self, prompt: str, image, phase: str) -> dict | None:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image]
            )
            raw = response.text.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                print(f"❌ Gemini returned no JSON for {phase} phase.")
                print("Raw:", raw[:300])
                return None

            parsed = json.loads(match.group(0))
            print(f"\n🤖 Gemini [{phase}] discovered:")
            print(json.dumps(parsed, indent=2))
            return parsed

        except Exception as e:
            print(f"❌ Gemini error ({phase}): {e}")
            return None
        
    def extract_posts(self, page, blueprint: dict, base_url: str) -> list[dict]:
        selector     = blueprint.get("container_selector", "article")
        fields       = blueprint.get("fields", {})
        url_field    = fields.get("url")
        title_field  = fields.get("title")
        author_field = fields.get("author")
        score_field  = fields.get("score")
        time_field   = fields.get("timestamp")
        site_type    = blueprint.get("site_type", "other")

        containers = page.locator(selector).all()
        print(f"\n📦 Found {len(containers)} containers → '{selector}'")

        posts = []
        for c in containers[:15]:
            try:
                def get_field(f, _c=c):
                    if not f:
                        return "N/A"
                    val = _c.get_attribute(f)
                    if val:
                        return val.strip()
                    try:
                        loc = _c.locator(f).first
                        if loc.count() > 0:
                            val = loc.inner_text(timeout=1000)
                            return val.strip() if val else "N/A"
                    except:
                        pass
                    return "N/A"

                raw_url = get_field(url_field)

                if raw_url != "N/A":
                    if raw_url.startswith("http"):
                        full_url = raw_url
                    elif raw_url.startswith("/"):
                        domain_match = re.match(r'(https?://[^/]+)', base_url)
                        domain = domain_match.group(1) if domain_match else base_url
                        full_url = domain + raw_url
                    elif site_type == "reddit":
                        # Data-post-id looks like "t3_1rp5vjc" strip the type prefix
                        post_id = re.sub(r'^t\d+_', '', raw_url)
                        full_url = f"https://www.reddit.com/comments/{post_id}"
                    else:
                        full_url = base_url.rstrip('/') + '/' + raw_url
                else:
                    full_url = "N/A"

                posts.append({
                    "title":        get_field(title_field),
                    "url":          full_url,
                    "author":       get_field(author_field),
                    "score":        get_field(score_field),
                    "timestamp":    get_field(time_field),
                    "body":         "N/A",
                    "top_comment":  "N/A",
                    "all_comments": "N/A",
                })
            except Exception as e:
                print(f"  ⚠️ Skipped container: {e}")

        return posts


    def learn_detail_page(self, page, posts: list[dict], site_url: str) -> dict | None:
        sample_post = next((p for p in posts if p["url"] != "N/A"), None)
        if not sample_post:
            print("⚠️ No valid post URLs found.")
            return None

        print(f"\n🔬 Phase 2: Opening a real post to learn its structure:")
        print(f"   → {sample_post['url']}")

        try:
            # Domcontentloaded is enough reddit never reaches networkidle
            page.goto(sample_post["url"], wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)  # Let js render comments

            # Scroll down in steps to trigger lazy-loaded comments
            for _ in range(5):
                page.mouse.wheel(0, 700)
                time.sleep(1.5)

            domain  = re.sub(r'https?://(www\.)?', '', site_url).split('/')[0]
            ss_path = f"{domain}_detail_screenshot.png"
            page.screenshot(path=ss_path)
            print(f"📷 Detail screenshot → {ss_path}")

            # Use detail-focused html snapshot (targets comments/body elements)
            html_map = self.get_detail_snapshot(page)
            return self.discover_detail_structure(ss_path, html_map, site_url)

        except Exception as e:
            print(f"⚠️ Phase 2 failed: {e}")
            return None

    def enrich_posts(self, page, posts: list[dict], detail_blueprint: dict) -> list[dict]:
        body_sel           = detail_blueprint.get("body_selector") or ""
        single_comment_sel = detail_blueprint.get("single_comment_selector") or ""
        comment_text_sel   = detail_blueprint.get("comment_text_selector") or ""
        comment_author_sel = detail_blueprint.get("comment_author_selector") or ""

        for i, post in enumerate(posts):
            if post["url"] == "N/A":
                continue
            print(f"\n🚀 [{i+1}/{len(posts)}] {post['title'][:60]}...")
            try:
                page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
                time.sleep(2.5)
                for _ in range(3):
                    page.mouse.wheel(0, 600)
                    time.sleep(1)

                # Body text
                if body_sel:
                    try:
                        body_parts = page.locator(body_sel).all()
                        post["body"] = " ".join(
                            el.inner_text() for el in body_parts[:5]
                        ).strip()[:800] or "N/A"
                        print(f"   📝 Body: {post['body'][:80]}...")
                    except:
                        post["body"] = "N/A"

                # Comments
                if single_comment_sel:
                    try:
                        comment_els = page.locator(single_comment_sel).all()[:5]
                        comments = []
                        for cel in comment_els:
                            author = "N/A"
                            text   = "N/A"
                            if comment_author_sel:
                                try:
                                    author = cel.locator(comment_author_sel).first.inner_text(timeout=1000).strip()
                                except:
                                    pass
                            if comment_text_sel:
                                try:
                                    text = cel.locator(comment_text_sel).first.inner_text(timeout=1000).strip()[:200]
                                except:
                                    pass
                            if text != "N/A":
                                comments.append(f"{author}: {text}")

                        post["top_comment"]   = comments[0] if comments else "N/A"
                        post["all_comments"]  = " || ".join(comments) if comments else "N/A"
                        print(f"   💬 {len(comments)} comments extracted")
                    except Exception as e:
                        print(f"   ⚠️ Comment extraction failed: {e}")

            except Exception as e:
                print(f"   ⚠️ Failed to visit post: {e}")

        return posts


    def start(self, url: str, enrich: bool = True):
        domain      = re.sub(r'https?://(www\.)?', '', url).split('/')[0]
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{domain}_{timestamp}.csv"

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page    = context.new_page()

            # Load listing page
            print(f"\n🌐 Loading {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            input("\n📸 Scroll down to load posts, then press ENTER...")

            ss_path = f"{domain}_listing_screenshot.png"
            page.screenshot(path=ss_path)
            print(f"📷 Screenshot → {ss_path}")
            html_map = self.get_listing_snapshot(page)

            # Phase 1: discover listing structure
            print("\n🤖 Phase 1: Analyzing listing page...")
            listing_blueprint = self.discover_listing_structure(ss_path, html_map, url)
            if not listing_blueprint:
                print("❌ Phase 1 failed. Exiting.")
                browser.close()
                return

            # Extract posts from listing
            posts = self.extract_posts(page, listing_blueprint, url)
            if not posts:
                print("⚠️ No posts found.")
                browser.close()
                return
            print(f"\n✅ Extracted {len(posts)} posts from listing.")

                # Phase 2: learn detail page structure
            detail_blueprint = None
            if enrich:
                detail_blueprint = self.learn_detail_page(page, posts, url)

          
            if enrich and detail_blueprint:
                print(f"\n🔍 Visiting all {len(posts)} posts for body + comments...")
                posts = self.enrich_posts(page, posts, detail_blueprint)
            elif enrich:
                print("⚠️ Skipping enrich — Gemini could not discover detail structure.")

            # Save csv
            df = pd.DataFrame(posts)
            df.to_csv(output_file, index=False)
            print(f"\n💾 Saved {len(posts)} posts → {output_file}")
            print("\n" + df[["title", "author", "top_comment"]].to_string(index=False))

             
            blueprints = {"listing": listing_blueprint, "detail": detail_blueprint}
            bp_file = f"{domain}_blueprint.json"
            with open(bp_file, "w") as f:
                json.dump(blueprints, f, indent=2)
            print(f"📐 Blueprints saved → {bp_file}")

            browser.close()
            return df



if __name__ == "__main__":
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    scraper = UniversalScraper(api_key=GEMINI_API_KEY)

    TARGET = "https://www.reddit.com"
    # Target "https://twitter.com"
    # Target "https://news.ycombinator.com"

    scraper.start(url=TARGET, enrich=True)