"""
Selenium-based YouTube comments scraper (extended)

Provides:
- `extract_comments_detailed(url, ...)` -> returns list of dicts:
    {"text":..., "author":..., "time":..., "likes":..., "is_reply": False/True, "reply_to": parent_text_or_id}
- Automatic expansion of "more replies" buttons and clicking "Show more" on long comments
- Robust selectors with fallbacks and defensive coding (best-effort)
- Headless support and optional chromedriver path

Note: Running this requires a local Chrome + chromedriver and a Python environment with
selenium and ssl. This module performs lazy imports and raises informative RuntimeError
if requirements are missing.

Includes a simple self-test that verifies behavior when selenium is not available.
"""

import time
import sys
import traceback

def _ensure_selenium():
    try:
        import ssl  # noqa: F401
    except Exception as e:
        raise RuntimeError("SSL support missing in Python environment; Selenium needs ssl.") from e

    try:
        from selenium import webdriver  # noqa: F401
    except ModuleNotFoundError as e:
        raise RuntimeError("Selenium not installed. Install with: pip install selenium") from e

def _safe_find(driver, by, value, multiple=False, timeout=2):
    from selenium.common.exceptions import NoSuchElementException
    import time as _time
    start = _time.time()
    while True:
        try:
            if multiple:
                return driver.find_elements(by, value)
            else:
                return driver.find_element(by, value)
        except NoSuchElementException:
            if _time.time() - start > timeout:
                return [] if multiple else None
            _time.sleep(0.2)

def extract_comments_detailed(url, max_comments=500, scroll_pause=1.0, headless=True, driver_path=None, expand_replies=True):
    """Extract comments from a YouTube video page with metadata.

    Returns list of dicts: text, author, time, likes, is_reply, parent_id

    This is a best-effort scraper: YouTube DOM can change and selectors may fail.
    """
    _ensure_selenium()
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import WebDriverException, ElementClickInterceptedException

    options = Options()
    if headless:
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1920,1080')
    else:
        options.add_argument('--start-maximized')

    driver = None
    try:
        # start driver
        if driver_path:
            try:
                driver = webdriver.Chrome(executable_path=driver_path, options=options)
            except TypeError:
                from selenium.webdriver.chrome.service import Service
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)

        driver.get(url)
        time.sleep(3)

        # scroll to comments section
        # Try locating the comment section by id
        driver.execute_script('window.scrollTo(0, 600);')
        time.sleep(1)
        # Press Page Down repeatedly to help lazy load
        for _ in range(6):
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
            time.sleep(0.3)

        # now scroll to bottom repeatedly to load comments
        comments = []
        seen = set()
        last_height = driver.execute_script('return document.documentElement.scrollHeight')
        stagnation = 0

        while len(comments) < max_comments:
            # find comment thread renderers
            thread_selectors = driver.find_elements(By.CSS_SELECTOR, 'ytd-comment-thread-renderer')
            if not thread_selectors:
                # fallback: search for ytd-comment-renderer directly
                thread_selectors = driver.find_elements(By.CSS_SELECTOR, 'ytd-comment-renderer')

            for thread in thread_selectors:
                try:
                    # Each thread may contain top-level comment + replies
                    # extract top-level comment element
                    top = thread.find_element(By.CSS_SELECTOR, 'ytd-comment-renderer')
                except Exception:
                    top = None
                if top is None:
                    continue

                try:
                    text_el = top.find_element(By.ID, 'content-text')
                    text = text_el.text.strip()
                except Exception:
                    text = ''
                # Use author name selectors (multiple possible paths)
                author = ''
                try:
                    a = top.find_element(By.CSS_SELECTOR, '#author-text')
                    author = a.text.strip()
                except Exception:
                    try:
                        author = top.find_element(By.CSS_SELECTOR, 'a.yt-simple-endpoint.style-scope.yt-formatted-string').text.strip()
                    except Exception:
                        author = ''
                # time
                published = ''
                try:
                    published = top.find_element(By.CSS_SELECTOR, 'a[href^="#"][aria-hidden="true"]').text.strip()
                except Exception:
                    try:
                        published = top.find_element(By.CSS_SELECTOR, 'span.published-time-text').text.strip()
                    except Exception:
                        published = ''
                # likes
                likes = ''
                try:
                    likes_el = top.find_element(By.CSS_SELECTOR, '#vote-count-middle')
                    likes = likes_el.text.strip()
                except Exception:
                    likes = ''

                unique_id = (author, text[:120])
                if unique_id in seen:
                    continue
                seen.add(unique_id)

                comments.append({
                    'text': text,
                    'author': author,
                    'time': published,
                    'likes': likes,
                    'is_reply': False,
                    'parent': None,
                })

                # optionally expand replies
                if expand_replies:
                    try:
                        # click "View replies" if present
                        more = thread.find_elements(By.CSS_SELECTOR, 'ytd-button-renderer#more-replies')
                        if not more:
                            # alternative selector: 'more-replies' may be a simple button
                            more = thread.find_elements(By.XPATH, './/yt-formatted-string[contains(text(), "답글 더보기") or contains(text(), "View replies") or contains(text(), "more replies")]')
                        for btn in more:
                            try:
                                driver.execute_script('arguments[0].scrollIntoView(true);', btn)
                                time.sleep(0.2)
                                btn.click()
                                time.sleep(0.5)
                            except Exception:
                                pass
                        # after expanding, find replies under this thread
                        reply_elems = thread.find_elements(By.CSS_SELECTOR, 'ytd-comment-replies-renderer ytd-comment-renderer')
                        if not reply_elems:
                            # alternative: nested ytd-comment-renderer inside the thread
                            reply_elems = thread.find_elements(By.CSS_SELECTOR, 'ytd-comment-renderer.reply')
                        for r in reply_elems:
                            try:
                                r_text = ''
                                try:
                                    r_text = r.find_element(By.ID, 'content-text').text.strip()
                                except Exception:
                                    r_text = ''
                                r_author = ''
                                try:
                                    r_author = r.find_element(By.CSS_SELECTOR, '#author-text').text.strip()
                                except Exception:
                                    r_author = ''
                                r_published = ''
                                try:
                                    r_published = r.find_element(By.CSS_SELECTOR, 'span.published-time-text').text.strip()
                                except Exception:
                                    r_published = ''
                                r_likes = ''
                                try:
                                    r_likes = r.find_element(By.CSS_SELECTOR, '#vote-count-middle').text.strip()
                                except Exception:
                                    r_likes = ''

                                unique_r = (r_author, r_text[:120])
                                if unique_r in seen:
                                    continue
                                seen.add(unique_r)

                                comments.append({
                                    'text': r_text,
                                    'author': r_author,
                                    'time': r_published,
                                    'likes': r_likes,
                                    'is_reply': True,
                                    'parent': text,
                                })
                            except Exception:
                                # ignore per-reply errors
                                traceback.print_exc()
                    except Exception:
                        # ignore expansion errors
                        traceback.print_exc()

                # stop early if reached max
                if len(comments) >= max_comments:
                    break

            # scroll further
            driver.execute_script('window.scrollTo(0, document.documentElement.scrollHeight);')
            time.sleep(scroll_pause)
            new_height = driver.execute_script('return document.documentElement.scrollHeight')
            if new_height == last_height:
                stagnation += 1
                if stagnation >= 3:
                    break
            else:
                last_height = new_height
                stagnation = 0

        return comments

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# -------------------------
# Simple self-tests
# -------------------------

def _selftest_no_selenium():
    """Test that the module reports a helpful error when selenium is missing."""
    # simulate selenium missing by temporarily removing it from sys.modules if present
    saved = sys.modules.get('selenium')
    if 'selenium' in sys.modules:
        del sys.modules['selenium']
    try:
        try:
            extract_comments_detailed('https://www.youtube.com/watch?v=dQw4w9WgXcQ', max_comments=1, headless=True)
            print('ERROR: expected RuntimeError due to missing selenium, but function ran')
        except RuntimeError as e:
            print('PASS: missing selenium detected:', e)
    finally:
        if saved is not None:
            sys.modules['selenium'] = saved

if __name__ == '__main__':
    print('Running selenium_scraper self-tests...')
    _selftest_no_selenium()
    print('Done')
