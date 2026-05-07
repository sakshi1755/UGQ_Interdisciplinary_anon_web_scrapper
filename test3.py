# Import pandas as pd
# From playwright.sync_api import sync_playwright
# Import json
# Import re
# Import ollama
# Import base64
# Import time

# Class patterndiscoveryscraper:
# Def __init__(self, model"llava"):
# Self.model model

# Def get_element_map(self, page):
# """extracts a very detailed map of attributes to help ai find the url key."""
# Return page.evaluate("""
# () {
# Const elements array.from(document.queryselectorall('shreddit-post, [data-testid"post-container"], article'));
# Return json.stringify(elements.slice(0, 5).map(el {
# Const attrs {};
# // we grab every attribute name to ensure ai sees 'permalink', 'href', etc.
# For (let attr of el.attributes) { attrs[attr.name] attr.value; }
# Return {
# Tagname: el.tagname,
# Attributes: attrs,
# Text_sample: el.innertext?.substring(0, 50)
# };
# }));
# }
# """)

# Def ask_ai(self, screenshot_path, element_map):
# With open(screenshot_path, "rb") as f:
# Img base64.b64encode(f.read()).decode('utf-8')
        
# Prompt f"""
# [system: json only]
# Look at the screenshot and html data. i need to scrape the post list.
        
# Html data:
# {element_map}

# Task:
# 1. identify the 'container_tag' (e.g., 'shreddit-post').
# 2. identify the exact attribute name that contains the link/url (e.g., 'permalink' or 'content-href').
# 3. identify the attribute names for: 'title', 'score', 'comment_count'.

# Return json:
# {{
# "container_tag": "tagname",
# "url_attr": "attribute_name",
# "title_attr": "attribute_name",
# "score_attr": "attribute_name",
# "comments_attr": "attribute_name"
# }}
# """
        
# Res ollama.chat(modelself.model, messages[{'role': 'user', 'content': prompt, 'images': [img]}])
# Try:
# Return json.loads(re.search(r'{.}', res['message']['content'], re.dotall).group(0))
# Except: return none

# Def start(self, url):
# With sync_playwright() as p:
# Browser p.chromium.launch(headlessfalse)
# Page browser.new_page()
# Page.goto(url)
# Input(" home page: scroll down so posts load, then press enter...")

# 1. feed discovery
# Page.screenshot(path"home.png")
# Home_map self.get_element_map(page)
# Print(" ai analyzing page patterns...")
# Logic self.ask_ai("home.png", home_map)

# If not logic:
# Print(" ai failed to return logic."); browser.close(); return

          
# Results []
# Container_tag logic.get('container_tag', 'shreddit-post').lower()
# Containers page.locator(container_tag).all()
            
# Print(f" found {len(containers)} containers. extracting deep data...")

# For i, c in enumerate(containers[:10]):
               
# Url_path c.get_attribute(logic.get('url_attr', 'permalink')) or c.get_attribute('permalink')
                
# If url_path:
# Full_url url_path if url_path.startswith('http') else f"https://www.reddit.com{url_path}"
                    
                   
# Post_data {
# "title": c.get_attribute(logic.get('title_attr', 'post-title')) or "n/a",
# "score": c.get_attribute(logic.get('score_attr', 'score')) or "n/a",
# "comments": c.get_attribute(logic.get('comments_attr', 'comment-count')) or "n/a",
# "url": full_url
# }
                    
                  
# Try:
                       
# Detail_page browser.new_page()
# Detail_page.goto(full_url, timeout10000)
                        
# Comment detail_page.locator("shreddit-comment p").first.inner_text(timeout3000)
# Post_data["top_comment"] comment
# Detail_page.close()
# Except:
# Post_data["top_comment"] "n/a"
# If 'detail_page' in locals(): detail_page.close()

# Results.append(post_data)
# Print(f" scraped: {post_data['title'][:40]}...")

# If results:
# Pd.dataframe(results).to_csv("reddit_final.csv", indexfalse)
# Print("n done! results saved to reddit_final.csv")
            
# Browser.close()

# If __name__ "__main__":
# Patterndiscoveryscraper().start("https://www.reddit.com")