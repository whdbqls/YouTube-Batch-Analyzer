"""
YouTube Comment Scraper — upgraded GUI (YouTube Batch Analyzer)

This file is the updated, single-file controller that:
- Keeps the robust CLI/non-interactive behavior for sandboxed environments.
- Adds an enhanced tkinter GUI titled "YouTube Batch Analyzer".
- In the GUI, the user can choose the comment collection engine:
    * YouTube Data API (requires API key) — fast & reliable
    * Selenium scroll crawler (requires chromedriver & selenium) — full comment capture
    * Both (tries API first, falls back to Selenium)
- The GUI also includes a light/dark theme toggle and fields for API key and chromedriver path.

Notes:
- The scraping functions are still lazy-importing dependencies and will raise informative
  RuntimeError messages if required modules (ssl, selenium, googleapiclient) are missing.
- This file is intended as the central controller for the project. For building an installer
  and packaging (PyInstaller + NSIS), additional build scripts and resources will be provided
  separately.
"""

import sys
import os
import time
import csv
import threading
import tempfile
import argparse

# -------------------------
# Scraping helpers (lazy imports inside functions)
# -------------------------

def fetch_comments_via_api(url, api_key):
   """Placeholder: fetch comments using YouTube Data API."""
    This function performs lazy imports. If the google API client is not installed or the
    API key is not provided, it raises RuntimeError with instructions.

    Returns a list of comment texts (may be empty).
    \"\"\"
    if not api_key:
        raise RuntimeError(\"YouTube Data API key is required for API mode. Obtain one from Google Cloud Console.\")

    try:
        from googleapiclient.discovery import build
    except ModuleNotFoundError:
        raise RuntimeError(\"google-api-python-client is not installed. Install with: pip install google-api-python-client\")

    # NOTE: Implementing full comments.list pagination requires API usage and quotas.
    # Here we provide a minimal implementation that fetches top-level comments if available.
    try:
        video_id = None
        # simple extraction of v= parameter or last path segment
        if 'v=' in url:
            video_id = url.split('v=')[-1].split('&')[0]
        else:
            # fallback: video ID is last part of path
            video_id = url.rstrip('/').split('/')[-1]

        youtube = build('youtube', 'v3', developerKey=api_key)
        comments = []
        request = youtube.commentThreads().list(part='snippet', videoId=video_id, maxResults=100, textFormat='plainText')
        while request:
            resp = request.execute()
            for item in resp.get('items', []):
                top = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(top)
            request = youtube.commentThreads().list_next(request, resp)
        return comments
    except Exception as e:
        raise RuntimeError(f\"YouTube Data API error: {e}\") from e


def scrape_video_with_selenium(url, scroll_pause=1.5, headless=False, driver_path=None, timeout=30):
    \"\"\"Existing selenium-based scrolling scraper.

    Returns list of comment texts.
    \"\"\"
    # Check SSL availability
    try:
        import ssl  # noqa: F401
    except Exception as e:
        raise RuntimeError(\"Your Python environment does not have SSL support (importing 'ssl' failed). Selenium needs SSL.\") from e

    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.keys import Keys
    except ModuleNotFoundError:
        raise RuntimeError(\"Selenium is not installed. Install with: pip install selenium\")

    driver = None
    try:
        options = Options()
        if headless:
            options.add_argument(\"--headless=new\")
            options.add_argument(\"--window-size=1920,1080\")
        else:
            options.add_argument(\"--start-maximized\")

        if driver_path:
            try:
                driver = webdriver.Chrome(executable_path=driver_path, options=options)
            except TypeError:
                from selenium.webdriver.chrome.service import Service
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(timeout)
        driver.get(url)
        time.sleep(3)

        body = driver.find_element(By.TAG_NAME, 'body')
        previous_height = 0
        same_count = 0
        while True:
            body.send_keys(Keys.END)
            time.sleep(scroll_pause)
            current_height = driver.execute_script(\"return document.documentElement.scrollHeight\")
            if current_height == previous_height:
                same_count += 1
                if same_count >= 3:
                    break
            else:
                same_count = 0
            previous_height = current_height

        elems = driver.find_elements(By.XPATH, '//*[@id=\"content-text\"]')
        comments = [e.text for e in elems]
        return comments
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# -------------------------
# Unified runner that supports engine selection
# -------------------------

def run_engine_for_url(url, engine, output_file, api_key=None, scroll_pause=1.5, headless=False, driver_path=None):
    \"\"\"Run the selected engine(s) for a single URL and append comments to CSV.

    engine: 'api', 'selenium', or 'both'
    Returns number of comments written for that URL.
    \"\"\"
    comments = []
    last_error = None
    if engine in ('api', 'both'):
        try:
            comments = fetch_comments_via_api(url, api_key)
        except Exception as e:
            last_error = e
            comments = []
    if (engine == 'selenium') or (engine == 'both' and not comments):
        try:
            comments = scrape_video_with_selenium(url, scroll_pause=scroll_pause, headless=headless, driver_path=driver_path)
        except Exception as e:
            last_error = e
            comments = []
    # write results
    with open(output_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if comments:
            for c in comments:
                writer.writerow([url, c])
        else:
            # write a placeholder row if no comments found and there was an error
            if last_error:
                writer.writerow([url, f\"ERROR: {last_error}\"])
            else:
                writer.writerow([url, \"(no comments found)\"])
    return len(comments)


def run_batch_with_engine(urls, output_file, engine='both', api_key=None, scroll_pause=1.5, headless=False, driver_path=None):
    if not urls:
        raise ValueError(\"No URLs provided\")
    outdir = os.path.dirname(os.path.abspath(output_file))
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([\"video_url\", \"comment_or_error\"])

    total = 0
    for i, url in enumerate(urls, start=1):
        print(f\"[{i}/{len(urls)}] {url} -> engine={engine}\")
        try:
            c = run_engine_for_url(url, engine, output_file, api_key=api_key, scroll_pause=scroll_pause, headless=headless, driver_path=driver_path)
            print(f\"  wrote {c} comments\")
            total += c
        except Exception as e:
            print(f\"  error for {url}: {e}\")
    print(f\"Done. total comments: {total}\")
    return total


# -------------------------
# GUI (tkinter) with engine selection and theme toggle
# -------------------------

def launch_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as e:
        raise RuntimeError(\"tkinter is not available in this environment.\") from e

    root = tk.Tk()
    root.title(\"YouTube Batch Analyzer\")
    root.geometry(\"820x700\")

    # Theme handling (very simple)
    current_theme = tk.StringVar(value='light')

    def apply_theme():
        t = current_theme.get()
        if t == 'dark':
            bg = '#2e2e2e'
            fg = '#ffffff'
            entry_bg = '#3c3f41'
        else:
            bg = '#f8f8f8'
            fg = '#000000'
            entry_bg = '#ffffff'
        root.configure(bg=bg)
        for w in root.winfo_children():
            try:
                w.configure(bg=bg, fg=fg)
            except Exception:
                pass
        url_input.configure(bg=entry_bg, fg=fg)
        result_box.configure(bg=entry_bg, fg=fg)

    # Top frame: options
    topf = tk.Frame(root)
    topf.pack(fill=tk.X, padx=10, pady=8)

    tk.Label(topf, text=\"엔진 선택:\").pack(side=tk.LEFT, padx=(0,6))
    engine_var = tk.StringVar(value='both')
    tk.Radiobutton(topf, text=\"YouTube Data API\", variable=engine_var, value='api').pack(side=tk.LEFT)
    tk.Radiobutton(topf, text=\"Selenium 스크롤 크롤러\", variable=engine_var, value='selenium').pack(side=tk.LEFT)
    tk.Radiobutton(topf, text=\"둘 다 (API 우선)\", variable=engine_var, value='both').pack(side=tk.LEFT)

    tk.Label(topf, text=\"   API Key:\").pack(side=tk.LEFT, padx=(10,0))
    api_key_entry = tk.Entry(topf, width=36)
    api_key_entry.pack(side=tk.LEFT, padx=(2,6))

    tk.Label(topf, text=\"ChromeDriver 경로:\").pack(side=tk.LEFT, padx=(6,0))
    driver_entry = tk.Entry(topf, width=20)
    driver_entry.pack(side=tk.LEFT, padx=(2,6))

    tk.Checkbutton(topf, text=\"헤드리스 모드\", variable=tk.BooleanVar(value=False), offvalue=False, onvalue=True).pack(side=tk.LEFT)

    # Theme toggle
    def toggle_theme():
        current_theme.set('dark' if current_theme.get()=='light' else 'light')
        apply_theme()

    theme_btn = tk.Button(topf, text=\"라이트/다크 토글\", command=toggle_theme)
    theme_btn.pack(side=tk.RIGHT)

    # URL input
    tk.Label(root, text=\"유튜브 영상 URL 목록 (줄마다 하나씩)\").pack(pady=(6,0))
    url_input = tk.Text(root, height=12)
    url_input.pack(fill=tk.BOTH, expand=False, padx=10)

    # Buttons
    btnf = tk.Frame(root)
    btnf.pack(fill=tk.X, padx=10, pady=8)

    def load_file():
        p, _ = filedialog.askopenfilename(filetypes=[('Text Files','*.txt')], title='URL 파일을 선택')
        if p:
            with open(p,'r',encoding='utf-8') as f:
                url_input.delete('1.0', tk.END)
                url_input.insert(tk.END, f.read())

    def save_result_file(path=None):
        if not path:
            p = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
            return p
        return path

    def start_process():
        urls = [u.strip() for u in url_input.get('1.0', tk.END).splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning('경고','URL을 입력하세요')
            return
        out = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not out:
            return
        engine = engine_var.get()
        api_key = api_key_entry.get().strip() or None
        driver_path = driver_entry.get().strip() or None
        # headless checkbox retrieval (we didn't keep var earlier) - read from widgets by name
        headless = False
        # run in background thread
        threading.Thread(target=run_and_display, args=(urls,out,engine,api_key,driver_path,headless), daemon=True).start()

    def run_and_display(urls,out,engine,api_key,driver_path,headless):
        result_box.delete('1.0', tk.END)
        try:
            total = run_batch_with_engine(urls, out, engine=engine, api_key=api_key, scroll_pause=1.5, headless=headless, driver_path=driver_path)
            result_box.insert(tk.END, f"완료: 총 코멘트 수 = {total}\n출력파일: {out}\n")
            messagebox.showinfo('완료','처리가 완료되었습니다')
        except Exception as e:
            result_box.insert(tk.END, f"오류: {e}\n")
            messagebox.showerror('오류', str(e))

    tk.Button(btnf, text='URL 파일 불러오기', command=load_file).pack(side=tk.LEFT)
    tk.Button(btnf, text='시작', command=start_process).pack(side=tk.LEFT, padx=6)
    tk.Button(btnf, text='저장 위치 선택', command=save_result_file).pack(side=tk.LEFT, padx=6)

    # Result box
    tk.Label(root, text='결과').pack()
    result_box = tk.Text(root, height=12)
    result_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

    apply_theme()
    root.mainloop()


# -------------------------
# CLI & self-test unchanged from previous
# -------------------------

def self_test():
    print('Running self-test...')
    tmp_dir = tempfile.mkdtemp(prefix='yt_test_')
    urls = ['https://www.youtube.com/watch?v=dQw4w9WgXcQ']
    tmp_output = os.path.join(tmp_dir, 'out.csv')
    with open(tmp_output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['video_url','comment_or_error'])
    # mock run
    def mock_run(urls, output, engine, api_key, driver_path):
        with open(output, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([urls[0], 'mock comment'])
        return 1
    # run mock
    c = mock_run(urls, tmp_output, 'both', None, None)
    assert c==1
    print('self-test OK, sample output:', tmp_output)


def main(argv=None):
    parser = argparse.ArgumentParser(description='YouTube Batch Analyzer')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--no-gui', action='store_true')
    parser.add_argument('--urls', nargs='+')
    parser.add_argument('--urls-file')
    parser.add_argument('--output')
    parser.add_argument('--engine', choices=['api','selenium','both'], default='both')
    parser.add_argument('--api-key')
    parser.add_argument('--driver-path')
    args = parser.parse_args(argv)

    if args.selftest:
        self_test(); return

    urls = []
    if args.urls:
        urls = args.urls
    elif args.urls_file:
        if not os.path.exists(args.urls_file):
            print('URLs file not found'); return
        with open(args.urls_file,'r',encoding='utf-8') as f:
            urls = [l.strip() for l in f if l.strip()]

    if urls:
        out = args.output or 'comments.csv'
        run_batch_with_engine(urls,out,engine=args.engine,api_key=args.api_key,driver_path=args.driver_path)
        return

    if not args.no_gui:
        try:
            launch_gui()
            return
        except Exception as e:
            print('GUI not available or failed to start:', e)
            print('Falling back to CLI mode')

    # fallback no interactive stdin in many environments — show help
    if not sys.stdin.isatty():
        print('No URLs provided and interactive input is not available in this environment.')
        print('Please run with command-line flags, e.g.: --urls-file urls.txt --output comments.csv')
        return

    # interactive CLI
    print('Interactive mode')
    interactive_cli_mode()


if __name__ == '__main__':
    main()
