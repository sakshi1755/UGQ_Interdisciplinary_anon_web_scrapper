from playwright.sync_api import sync_playwright
import requests
import os
import subprocess
import imageio_ffmpeg
import speech_recognition as sr

def solve_recaptcha_with_buster(page):
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    
    audio_path = "captcha.mp3"
    wav_path   = "captcha.wav"

    print(" Looking for CAPTCHA...")
    page.wait_for_timeout(2000)

   
    recaptcha_frame = page.frame_locator("iframe[title='reCAPTCHA']")
    checkbox = recaptcha_frame.locator("# #recaptcha-anchor")
    checkbox.wait_for(timeout=5000)
    checkbox.click()
    print(" Clicked the checkbox")
    page.wait_for_timeout(3000)

    # Click audio button
    challenge_frame = page.frame_locator("iframe[title='recaptcha challenge expires in two minutes']")
    audio_btn = challenge_frame.locator("# #recaptcha-audio-button")
    audio_btn.wait_for(timeout=5000)
    audio_btn.click()
    print(" Clicked audio button...")
    page.wait_for_timeout(2000)

    # Get audio url
    audio_link = challenge_frame.locator(".rc-audiochallenge-tdownload-link")
    audio_url = audio_link.get_attribute("href")
    print(f" Got audio URL: {audio_url[:60]}...")

    # Download audio
    r = requests.get(audio_url)
    with open(audio_path, "wb") as f:
        f.write(r.content)
    print(f"⬇️ Downloaded audio → {audio_path}")

    # Convert mp3 to wav using subprocess (fixes windows path issues)
    result = subprocess.run(
        [ffmpeg_exe, "-y", "-i", audio_path, wav_path],
        capture_output=True,
        text=True
    )

    if not os.path.exists(wav_path):
        print("❌ ffmpeg failed. Error:")
        print(result.stderr)
        return

    print(f" Converted to WAV → {wav_path}")

    # Transcribe
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
    text = recognizer.recognize_google(audio_data)
    print(f" Heard: '{text}'")

    # Type answer and verify
    answer_field = challenge_frame.locator("# #audio-response")
    answer_field.fill(text.lower())
    print(" Typed the answer...")

    verify_btn = challenge_frame.locator("# #recaptcha-verify-button")
    verify_btn.click()
    print(" Submitted! CAPTCHA should be solved!")
    page.wait_for_timeout(3000)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print(" Opening reCAPTCHA demo page...")
    page.goto("https://www.google.com/recaptcha/api2/demo", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    solve_recaptcha_with_buster(page)

    input("\n Check the browser — press ENTER to close...")
    browser.close()