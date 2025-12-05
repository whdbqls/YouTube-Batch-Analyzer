# Building YouTube Batch Analyzer (Windows)

Prerequisites:
- Python 3.8+ installed
- pip
- PyInstaller (installed automatically by build.py if missing)
- makensis (for NSIS installer) — optional
- A valid icon file: `assets/youtube_batch.ico` (place your .ico here)

Steps:
1. Place your entry file in project root, named `youtube_comment_scraper.py` (or adjust build.py --entry).
2. Place an .ico file at `assets/youtube_batch.ico`.
3. Run build script:
   ```bash
   python build.py --icon assets/youtube_batch.ico --name "YouTube Batch Analyzer" --nsis
   ```
4. If successful, `dist/` will contain the built exe and `YouTube Batch Analyzer Setup 1.0.0.exe` will be created by NSIS.

Troubleshooting:
- If PyInstaller fails due to missing libraries, ensure you installed all Python requirements.
- If makensis is not found, install NSIS and add `makensis` to your PATH.
