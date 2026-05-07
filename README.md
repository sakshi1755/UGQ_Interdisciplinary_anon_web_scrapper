# Anonymous AI Web Scraper 🕵️‍♂️🤖

An advanced, stealthy web scraping project that leverages **Playwright** and **Google Gemini 2.5 Flash Vision** to dynamically discover and extract content from websites (like Reddit, Twitter, HackerNews, etc.) without hardcoding CSS selectors.

## Features ✨

- **Dynamic Element Discovery**: Uses the Gemini API to analyze page screenshots and HTML mapping to find the correct CSS selectors for containers, titles, URLs, etc., on-the-fly.
- **Two-Phase Extraction**:
  - **Phase 1**: Learns the layout of a Feed/Listing page to extract post lists.
  - **Phase 2**: Visits individual post details to extract deep content like body text and top comments.
- **Stealth and Anti-Bot Evasion**: 
  - Integrates `playwright-stealth` to evade generic bot detection.
  - Uses randomized human-like scrolling, mouse movements, and reading delays.
  - Mimics hardware concurrency, plugins, and device memory properties.
- **Visual Web Scraper App**: A local web application to visually debug and scrape sites. Includes automated Audio ReCAPTCHA solving.

## Setup Instructions 🛠️

1. **Clone the repository** (if applicable).
2. **Set up a Virtual Environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install pandas playwright playwright-stealth google-genai pillow python-dotenv flask flask-cors imageio-ffmpeg SpeechRecognition requests
   playwright install chromium
   ```
4. **Environment Variables**:
   Create a `.env` file in the root directory and add your Google Gemini API key:
   ```env
   GEMINI_API_KEY="your_actual_api_key_here"
   ```

## The Scripts Explained 📄

Here is a breakdown of the core Python scripts in the project:

### 1. The Universal Scrapers
- **`universal_ai_ss.py`**: A generic AI-driven scraper designed to work across multiple platforms (Reddit, Twitter, HN). It operates in two phases: first analyzing a listing page, then visiting individual posts.
- **`univeral_Ai_ss(better).py`**: An improved version of the universal scraper. This version specifically mounts a temporary copy of your **real Chrome profile** (`User Data\Default`) to inherit cookies and local storage. This allows it to easily bypass logins and generic bot blocks.

### 2. The Reddit Scrapers
- **`Reddit_gemini_ss.py`**: A lightweight, straightforward script that targets Reddit using a single screenshot. It asks Gemini to figure out the scraping logic and visits the top 10 posts.
- **`stealth_reddit_better.py`**: A highly stealthy Reddit scraper. It applies heavy anti-bot evasion like human-like scrolling (`human_scroll`), randomized mouse movements (`human_mouse_move`), and fake hardware APIs to appear as a genuine user. 
- **`stealth_reddit(to prevent captcha).py`**: The most robust anti-captcha scraper. It warms up the browser by visiting Google first, uses custom viewport settings, modifies HTTP headers, and utilizes extensive randomized delays to drastically lower the chance of triggering Cloudflare or Reddit's captcha systems.
- **`manual_reddit_scraping.py`** & **`test3.py`**: Older or specialized testing scripts used for debugging layout extraction and scraper mechanics.

### 3. The Visual Scraper App (The `app/` Folder)
The `app` directory contains a full-stack local web application for visual scraping and debugging:
- **`app/backend.py`**: A **Flask** API server driving Playwright in headed mode. It uses your actual Chrome profile to bypass bot detection. 
  - *Automated CAPTCHA Solver*: If it hits a reCAPTCHA, it automatically clicks the Audio Challenge, downloads the audio using `requests`, converts it to WAV via `FFmpeg`, and uses `SpeechRecognition` to solve and type the code.
  - *API Routes*: Features endpoints like `/fetch-page` to get the rendered DOM, `/scrape` to execute dynamic CSS extractions, and `/inspect-element` to extract attributes for AI consumption.
- **`app/visual-scraper.html`**: The frontend UI for the backend. Allows you to input a URL, visually inspect the page structure, view screenshots, and test AI-discovered selectors manually via the local server.

## Understanding the Outputs 📁

When running the scripts, you will generate several types of output files:

- **Data Tables (`*.csv`)**: The primary result of your scrapes (e.g., `reddit_test5.csv`, `twitter.com_20260310_...csv`). These Pandas-generated CSVs contain the structured output: Titles, URLs, Author, Top Comments, and Upvotes.
- **AI Blueprints (`*_blueprint.json`)**: Whenever Gemini discovers the HTML structure of a website, the logic is saved here. Instead of asking the AI every time, you can reuse this blueprint for faster, cheaper scraping on the same site layout.
- **Screenshots (`*.png`)**: Visual captures used by Gemini to 'see' the page layout (e.g., `home.png`, `reddit.com_detail_screenshot.png`). It also captures `blocked.png` if Cloudflare intercepts the scraper, helping you debug failures.
- **Audio Files (`captcha.mp3`, `captcha.wav`)**: Temporary audio files generated by the Visual Scraper backend when automatically solving Google reCAPTCHAs via the audio challenge.

> **Note**: Your `.env` API keys, virtual environments, and all output data files are securely excluded from version control via `.gitignore`.
