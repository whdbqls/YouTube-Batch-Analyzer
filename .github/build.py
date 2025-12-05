#!/usr/bin/env python3
"""
Automated build script for YouTube Batch Analyzer (Windows).

What it does:
- Verifies required tools (pyinstaller, pip)
- Installs Python deps into a venv (optional)
- Runs PyInstaller to build a single-file, windowed exe
- Produces a distribution folder with exe and ancillary files
- Optionally runs the NSIS compiler to create an installer

Usage:
    python build.py --icon assets/youtube_batch.ico --name "YouTube Batch Analyzer" --nsis
