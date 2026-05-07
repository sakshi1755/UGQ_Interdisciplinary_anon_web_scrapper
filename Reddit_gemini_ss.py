# #this is only reddit by one screenshot from gemini ai
import pandas as pd
from playwright.sync_api import sync_playwright
import json
import re
import time
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

            # Strip markdown code fences if gemini adds them
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

            # Extract json object
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
            browser = p.chromium.launch(headless=False)

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Load the homepage
            print(f" Loading {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            input("\n HOME PAGE LOADED: Scroll down a bit, then press ENTER to continue...")

            page.screenshot(path="home.png")
            home_map = self.get_element_map(page)

            # Ask gemini to discover the scraping pattern
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
            for c in containers[:10]:
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

            # Visit each post and grab the top comment
            results = []
            for i, post in enumerate(posts_to_visit):
                print(f" [{i+1}/{len(posts_to_visit)}] Visiting: {post['title'][:50]}...")
                try:
                    page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)
                    page.mouse.wheel(0, 800)

                    comment_loc = page.locator("shreddit-comment p").first
                    post["top_comment"] = (
                        comment_loc.inner_text(timeout=3000)
                        if comment_loc.count() > 0
                        else "N/A"
                    )
                    results.append(post)
                    print(f"   Top comment: {post['top_comment'][:60]}...")

                except Exception as e:
                    post["top_comment"] = f"ERROR: {e}"
                    results.append(post)
                    print(f"     Failed: {e}")

            # Save results
            if results:
                df = pd.DataFrame(results)
                df.to_csv("reddit_final.csv", index=False)
                print(f"\n Saved {len(results)} posts → reddit_final.csv")
                print(df[["title", "score", "comments"]].to_string(index=False))
            else:
                print(" No results to save.")

            browser.close()


# Entry point
if __name__ == "__main__":
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment.")

    scraper = PatternDiscoveryScraper(api_key=GEMINI_API_KEY)
    scraper.start("https://www.reddit.com")
