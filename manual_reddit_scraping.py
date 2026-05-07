from playwright.sync_api import sync_playwright
import pandas as pd
import time
import random
import re

data = []

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir="reddit_profile",
        headless=False
    )
    page = browser.new_page()
    
    
    page.goto("https://www.reddit.com/")
    
    input("Solve captcha/login if needed → press ENTER...")
 
    page.wait_for_selector("shreddit-post", timeout=10000)
    
    
    posts = page.query_selector_all("shreddit-post")
    links = []
    
    for post in posts[:10]:
      
        link = post.get_attribute("permalink")
        if not link:
            # Fallback: try to find link inside the post
            link_elem = post.query_selector("a[slot='full-post-link']")
            if link_elem:
                link = link_elem.get_attribute("href")
        
        if link:
            if not link.startswith("http"):
                link = "https://reddit.com" + link
            links.append(link)
    
    print(f"\nFound {len(links)} posts")
   
    for url in links:
        print("\nVisiting:", url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
          
            page.wait_for_selector("h1, [slot='title']", timeout=10000)
            time.sleep(random.uniform(2, 4))
            
           
            title = "N/A"
            title_selectors = [
                "h1[slot='title']",
                "h1",
                "[slot='title']",
                "shreddit-post h1"
            ]
            
            for selector in title_selectors:
                try:
                    elem = page.locator(selector).first
                    if elem:
                        title = elem.inner_text(timeout=2000)
                        if title and title.strip():
                            break
                except:
                    continue
            
           
            score = "N/A"
            
            # Strategy 1: look for score in shreddit-post attribute
            post_elem = page.locator("shreddit-post").first
            if post_elem:
                score_attr = post_elem.get_attribute("score")
                if score_attr:
                    score = score_attr
            
            # Strategy 2: look for upvote button aria-label
            if score == "N/A":
                try:
                    vote_btns = page.locator("button[aria-label*='vote']").all()
                    for btn in vote_btns:
                        label = btn.get_attribute("aria-label") or ""
                        # Match patterns like "upvote 1234" or "upvoted 1234"
                        match = re.search(r'(\d+)', label)
                        if match:
                            score = match.group(1)
                            break
                except:
                    pass
            
            # Strategy 3 look for score in faceplate-number
            if score == "N/A":
                try:
                    score_elem = page.locator("faceplate-number").first
                    if score_elem:
                        score_text = score_elem.get_attribute("number")
                        if score_text:
                            score = score_text
                except:
                    pass
            
           
            comment_count = "0"
            
            # Strategy 1 look in shreddit-post attribute
            if post_elem:
                count_attr = post_elem.get_attribute("comment-count")
                if count_attr:
                    comment_count = count_attr
            
            # Strategy 2 look for comment link text
            if comment_count == "0":
                try:
                    comment_selectors = [
                        "a[href*='comments']",
                        "button[aria-label*='comment']",
                        "[class*='comment'] faceplate-number"
                    ]
                    
                    for selector in comment_selectors:
                        elems = page.locator(selector).all()
                        for elem in elems:
                            text = elem.inner_text(timeout=1000) or ""
                            label = elem.get_attribute("aria-label") or ""
                            combined = text + " " + label
                            
                           
                            match = re.search(r'(\d+)', combined)
                            if match:
                                comment_count = match.group(1)
                                break
                        
                        if comment_count != "0":
                            break
                except:
                    pass
            
           
            top_comment = "No comments"
            
          
            time.sleep(1)
            
            comment_selectors = [
                "[slot='comment']",
                "shreddit-comment",
                "[data-testid='comment']",
                ".Comment"
            ]
            
            for selector in comment_selectors:
                try:
                    comments = page.locator(selector).all()
                    if comments:
                     
                        for comment in comments[:5]:
                           
                            html = comment.inner_html()
                            if "promoted" in html.lower() or "advertisement" in html.lower():
                                continue
                            
                            text = comment.inner_text(timeout=2000)
                            if text and len(text.strip()) > 10:
                                top_comment = text[:300]
                                break
                        
                        if top_comment != "No comments":
                            break
                except:
                    continue
            
            print(f"Title: {title[:60]}")
            print(f"Score: {score}")
            print(f"Comments: {comment_count}")
            print(f"Top comment: {top_comment[:80]}...")
            
            data.append({
                "url": url,
                "title": title,
                "score": score,
                "num_comments": comment_count,
                "top_comment": top_comment
            })
            
        except Exception as e:
            print(f"Error on {url}: {e}")
            data.append({
                "url": url,
                "title": "ERROR",
                "score": "ERROR",
                "num_comments": "ERROR",
                "top_comment": str(e)
            })
        
     
        time.sleep(random.uniform(3, 5))
    
    browser.close()

 
df = pd.DataFrame(data)
df.to_csv("reddit_home_data.csv", index=False)
print("\n Saved → reddit_home_data.csv")
print(f"\nScraped {len(data)} posts")