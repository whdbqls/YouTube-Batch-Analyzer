"""
YouTube Data API comments collector (robust, paginated, resumable)

Features:
- Fetch all top-level comments (and optionally replies) using YouTube Data API v3
- Handles pagination (nextPageToken), rate limit retry with exponential backoff
- Resumable progress: writes intermediate results to a JSONL checkpoint file
- Can limit max_comments to avoid exhausting quota during tests
- Lazy-imports googleapiclient and raises clear errors when missing

Usage:
    from youtube_api_scraper import fetch_comments_for_video
    comments = fetch_comments_for_video(video_id, api_key, max_comments=1000, include_replies=True)

Returned value: list of dicts with keys: comment_id, author, text, published_at, like_count, parent_id (None for top-level)

Note: This module requires the `google-api-python-client` package and a valid API key with YouTube Data API enabled.
"""

import time
import json
import os
import math

class YouTubeAPIError(Exception):
    pass

def _build_service(api_key):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ModuleNotFoundError as e:
        raise YouTubeAPIError("google-api-python-client not installed. Install: pip install google-api-python-client") from e

    try:
        service = build('youtube', 'v3', developerKey=api_key)
        return service
    except Exception as e:
        raise YouTubeAPIError(f"Failed to build YouTube service: {e}") from e

def _safe_execute(request, max_retries=6, initial_delay=1.0):
    """Execute Google API request with exponential backoff on quota/500 errors."""
    from googleapiclient.errors import HttpError
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return request.execute()
        except HttpError as e:
            status = getattr(e, 'status_code', None) or (e.resp.status if hasattr(e, 'resp') else None)
            # 403 might indicate quota; 429 too; 5xx transient
            if status in (403, 429) or (status and 500 <= int(status) < 600):
                wait = delay * (2 ** attempt)
                sleeptime = min(60, wait)
                print(f"HTTP {status} — retrying after {sleeptime} seconds... (attempt {attempt+1})")
                time.sleep(sleeptime)
                continue
            raise
        except Exception:
            # non-HTTP errors: maybe network; backoff and retry
            wait = delay * (2 ** attempt)
            sleeptime = min(60, wait)
            print(f"Request error — retrying after {sleeptime} seconds... (attempt {attempt+1})")
            time.sleep(sleeptime)
    raise YouTubeAPIError("Max retries exceeded for API request")

def fetch_comments_for_video(video_id, api_key, include_replies=False, max_comments=None, checkpoint_path=None):
    """Fetch comments for a single video_id using YouTube Data API.

    Args:
      video_id (str): YouTube video ID
      api_key (str): API key with YouTube Data API enabled
      include_replies (bool): if True, also fetch replies to top-level comments
      max_comments (int|None): stop after collecting this many comments
      checkpoint_path (str|None): JSONL file path to save progress periodically

    Returns:
      list of dicts: each dict contains comment_id, author, text, published_at, like_count, parent_id
    """
    if not api_key:
        raise YouTubeAPIError('API key required')

    service = _build_service(api_key)

    collected = []
    if checkpoint_path and os.path.exists(checkpoint_path):
        # load checkpoint
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    collected.append(obj)
                except Exception:
                    pass
        print(f"Resumed from checkpoint: loaded {len(collected)} comments")

    # top-level commentThreads.list
    next_page_token = None
    fetched = 0

    while True:
        req = service.commentThreads().list(
            part='snippet,replies',
            videoId=video_id,
            pageToken=next_page_token,
            maxResults=100,
            textFormat='plainText'
        )
        resp = _safe_execute(req)
        items = resp.get('items', [])
        for thread in items:
            snippet = thread.get('snippet', {})
            top = snippet.get('topLevelComment', {}).get('snippet', {})
            comment_id = thread.get('id')
            entry = {
                'comment_id': top.get('id') or comment_id,
                'author': top.get('authorDisplayName'),
                'text': top.get('textDisplay'),
                'published_at': top.get('publishedAt'),
                'like_count': top.get('likeCount'),
                'parent_id': None,
            }
            collected.append(entry)
            fetched += 1

            # optional replies included in the thread payload
            if include_replies:
                replies = thread.get('replies', {}).get('comments', [])
                for r in replies:
                    s = r.get('snippet', {})
                    re = {
                        'comment_id': r.get('id'),
                        'author': s.get('authorDisplayName'),
                        'text': s.get('textDisplay'),
                        'published_at': s.get('publishedAt'),
                        'like_count': s.get('likeCount'),
                        'parent_id': entry['comment_id'],
                    }
                    collected.append(re)
                    fetched += 1

                # periodic checkpoint
                if checkpoint_path and (len(collected) % 50 == 0):
                    with open(checkpoint_path, 'a', encoding='utf-8') as f:
                        for obj in collected[-50:]:
                            f.write(json.dumps(obj, ensure_ascii=False) + '\n')
                    print(f"Checkpoint saved: {checkpoint_path} (total {len(collected)})")

                if max_comments and fetched >= max_comments:
                    print(f"Reached max_comments={max_comments}")
                    # final checkpoint
                    if checkpoint_path:
                        with open(checkpoint_path, 'a', encoding='utf-8') as f:
                            for obj in collected[-(fetched if fetched<50 else 50):]:
                                f.write(json.dumps(obj, ensure_ascii=False) + '\n')
                    return collected

        next_page_token = resp.get('nextPageToken')
        if not next_page_token:
            break
    # final checkpoint
    if checkpoint_path and collected:
        with open(checkpoint_path, 'a', encoding='utf-8') as f:
            for obj in collected[-(len(collected) if len(collected)<50 else 50):]:
                f.write(json.dumps(obj, ensure_ascii=False) + '\n')
        print(f"Final checkpoint saved: {checkpoint_path}")

    return collected

# -------------------------
# Small self-test that does NOT require a real API key — uses mocking if googleapiclient missing
# -------------------------
def _selftest_mock():
    print('Running self-test (mock)')
    # If googleapiclient is not available, create a mock service object
    try:
        from googleapiclient.discovery import build  # noqa: F401
        real = True
    except Exception:
        real = False

    if real:
        print('googleapiclient available — skipping mock self-test (requires real API key)')
        return

    # create a fake service with commentThreads().list().execute() chaining
    class FakeRequest:
        def __init__(self, items, next_token=None):
            self._items = items
            self._next = next_token
        def execute(self):
            return {'items': self._items, 'nextPageToken': self._next}

    class FakeThreads:
        def __init__(self, pages):
            self.pages = pages
            self.i = 0
        def list(self, **kwargs):
            page = self.pages[self.i]
            self.i += 1
            next_token = None
            if self.i < len(self.pages):
                next_token = 'token'
            return FakeRequest(page, next_token)

    class FakeService:
        def __init__(self, pages):
            self._threads = FakeThreads(pages)
        def commentThreads(self):
            return self._threads

    pages = [
        [{'id':'t1','snippet':{'topLevelComment':{'snippet':{'id':'c1','authorDisplayName':'A','textDisplay':'hello','publishedAt':'2020-01-01T00:00:00Z','likeCount':1}}}}],
        [{'id':'t2','snippet':{'topLevelComment':{'snippet':{'id':'c2','authorDisplayName':'B','textDisplay':'world','publishedAt':'2020-01-02T00:00:00Z','likeCount':2}}}}]
    ]

    # monkeypatch _build_service to return our fake
    global _build_service
    orig_build = _build_service
    def fake_build(api_key):
        return FakeService(pages)
    _build_service = fake_build

    try:
        out = fetch_comments_for_video('dummvid', api_key='dummy', include_replies=False, max_comments=None, checkpoint_path=None)
        assert len(out) == 2, f'expected 2 comments, got {len(out)}'
        print('Mock self-test passed')
    finally:
        _build_service = orig_build

if __name__ == '__main__':
    _selftest_mock()
