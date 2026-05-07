# #this is stealth using only reddit gemini..i added random moments,goto google first and navigator
import pandas as pd
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import json
import re
import time
import random
from google import genai
from PIL import Image
import io
import os
from dotenv import load_dotenv

load_dotenv()

class PatternDiscoveryScraper:
    def __init__(self, api_key: str, model="gemini-2.5-flash"):
        self.model = model
        self.client = genai.Client(api_key=api_key)

   

    def human_delay(self, min_ms=500, max_ms=2000):
        """Random delay to mimic human reading/thinking time."""
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    def human_mouse_move(self, page):
        """Move mouse in a natural curved path across the page."""
        steps = random.randint(3, 7)
        for _ in range(steps):
            x = random.randint(100, 1200)
            y = random.randint(100, 700)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.05, 0.2))

    def human_scroll(self, page, total_px=800):
        """Scroll in small chunks like a human would."""
        scrolled = 0
        while scrolled < total_px:
            chunk = random.randint(100, 300)
            page.mouse.wheel(0, chunk)
            scrolled += chunk
            time.sleep(random.uniform(0.1, 0.4))


    def get_element_map(self, page):
        """Extract HTML structure of post containers from the page."""
        return page.evaluate("""
            () => {
                const elements = Array.from(document.querySelectorAll(
                    'shreddit-post, [data-testid="post-container"], article'
                ));
                return JSON.stringify(elements.slice(0, 5).map(el => {
                    const attrs = {};
                    for (let attr of el.attributes) { attrs[attr.name] = attr.value; }
                    return {
                        tagName: el.tagName,
                        attributes: attrs,
                        text_sample: el.innerText?.substring(0, 50)
                    };
                }));
            }
        """)

    def ask_ai(self, screenshot_path: str, element_map: str) -> dict | None:
        """
        Send screenshot + HTML map to Gemini Vision and get back
        the scraping logic (which attributes to use for title, url, etc.)
        """
        with open(screenshot_path, "rb") as f:
            image = Image.open(io.BytesIO(f.read()))

        prompt = f"""
You are a web scraping assistant. Look at the screenshot and the HTML data below.
I need to scrape a list of Reddit posts from this page.

HTML ELEMENT DATA (first 5 post containers):
{element_map}

YOUR TASK:
1. Identify the 'container_tag' — the HTML tag wrapping each post (e.g., 'SHREDDIT-POST').
2. Identify the EXACT attribute name that contains the post link/URL (e.g., 'permalink').
3. Identify the attribute names for: post title, score/upvotes, and comment count.

RESPOND WITH ONLY A VALID JSON OBJECT — no explanation, no markdown, no code fences:
{{
    "container_tag": "TAGNAME",
    "url_attr": "attribute_name",
    "title_attr": "attribute_name",
    "score_attr": "attribute_name",
    "comments_attr": "attribute_name"
}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image]
            )
            raw = response.text.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                print(" No JSON found in Gemini response.")
                print("Raw response:", raw)
                return None

            parsed = json.loads(match.group(0))
            print(" Gemini discovered scraping logic:", parsed)
            return parsed

        except Exception as e:
            print(f" Gemini API error: {e}")
            return None

   
    def start(self, url: str):
        with sync_playwright() as p:

            
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--start-maximized",
                ]
            )

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York",
                # Mimic real browser permissions
                permissions=["geolocation"],
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "keep-alive",
                }
            )

            page = context.new_page()

          
            Stealth().apply_stealth_sync(page)

            page.add_init_script("""
                // Remove webdriver flag
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

                // Spoof plugins (real browsers have plugins)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                // Spoof languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });

                // Spoof hardware concurrency (real CPU cores)
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                });

                // Spoof device memory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8,
                });

                // Fix chrome object (Playwright doesn't add this by default)
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };

                // Fix permissions API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
            """)

            print(" Warming up browser with a neutral page visit...")
            page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
            self.human_delay(1000, 2500)
            self.human_mouse_move(page)

            print(f" Loading {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.human_delay(2000, 4000)

            print(" Scrolling to load more posts...")
            for scroll_round in range(5):
                self.human_scroll(page, total_px=800)
                self.human_delay(1500, 2500)
                count = page.locator("shreddit-post").count()
                print(f"   Round {scroll_round+1}: {count} posts loaded so far...")
                if count >= 20:
                    break
            self.human_mouse_move(page)

            # Screenshot ai analysis
            page.screenshot(path="home.png")
            home_map = self.get_element_map(page)

            print("\n Asking Gemini to analyze the page structure...")
            logic = self.ask_ai("home.png", home_map)

            if not logic:
                print(" Could not determine scraping logic. Exiting.")
                browser.close()
                return

            # Extract post metadata
            container_tag = logic.get("container_tag", "shreddit-post").lower()
            url_attr      = logic.get("url_attr", "permalink")
            title_attr    = logic.get("title_attr", "post-title")
            score_attr    = logic.get("score_attr", "score")
            comments_attr = logic.get("comments_attr", "comment-count")

            containers = page.locator(container_tag).all()
            print(f"\n Found {len(containers)} post containers using tag: <{container_tag}>")

            posts_to_visit = []
            for c in containers[:25]:
                url_path = c.get_attribute(url_attr)
                if url_path:
                    full_url = (
                        url_path if url_path.startswith("http")
                        else f"https://www.reddit.com{url_path}"
                    )
                    posts_to_visit.append({
                        "title":    c.get_attribute(title_attr)    or "N/A",
                        "score":    c.get_attribute(score_attr)    or "N/A",
                        "comments": c.get_attribute(comments_attr) or "N/A",
                        "url":      full_url,
                    })

            print(f" Queued {len(posts_to_visit)} posts to visit.\n")

            # Visit each post with human-like behavior
            results = []
            for i, post in enumerate(posts_to_visit):
                print(f" [{i+1}/{len(posts_to_visit)}] Visiting: {post['title'][:50]}...")
                try:
                    # Random delay between page visits (key anti-bot signal)
                    self.human_delay(2000, 5000)

                    page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
                    self.human_delay(1000, 2500)

                    # Simulate reading behavior
                    self.human_mouse_move(page)
                    self.human_scroll(page, total_px=random.randint(400, 1000))
                    self.human_delay(500, 1500)

                    comment_loc = page.locator("shreddit-comment p").first
                    post["top_comment"] = (
                        comment_loc.inner_text(timeout=3000)
                        if comment_loc.count() > 0
                        else "N/A"
                    )
                    results.append(post)
                    print(f" Top comment: {post['top_comment'][:60]}...")

                except Exception as e:
                    post["top_comment"] = f"ERROR: {e}"
                    results.append(post)
                    print(f" Failed: {e}")

            # Save results
            if results:
                df = pd.DataFrame(results)
                df.to_csv("reddit_test5.csv", index=False)
                print(f"\n Saved {len(results)} posts → reddit_test5.csv")
                print(df[["title", "score", "comments"]].to_string(index=False))
            else:
                print(" No results to save.")

            browser.close()


if __name__ == "__main__":
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    scraper = PatternDiscoveryScraper(api_key=GEMINI_API_KEY)
    scraper.start("https://www.reddit.com")