import logging
import os
import time
import urllib.request
import warnings
from datetime import date
from typing import Callable, Optional
from urllib.parse import urlencode

import yt_dlp

# Suppress yt-dlp Python version deprecation noise
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("yt_dlp").setLevel(logging.CRITICAL)

from .models import DownloadJob, DownloadResult, DownloadStatus, Platform

_TIKWM_API = "https://www.tikwm.com/api/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


# ─── Output directory ──────────────────────────────────────────────────────────

def _build_output_dir(base_output: str, use_cwd: bool = False) -> str:
    if use_cwd:
        os.makedirs(base_output, exist_ok=True)
        return base_output
    today = date.today().strftime("%Y-%m-%d")
    output_dir = os.path.join(base_output, today)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


# ─── yt-dlp options ────────────────────────────────────────────────────────────

def _build_ydl_opts(output_dir: str, cookies_browser: Optional[str] = None, platform: str = "") -> dict:
    # YouTube no longer serves pre-merged MP4 via "best[ext=mp4]".
    # Format codes 22 (720p MP4) and 18 (360p MP4) are legacy pre-merged streams.
    fmt = "22/18/best[ext=mp4]/best" if "youtube" in platform.lower() else "best[ext=mp4]/best"

    opts: dict = {
        "outtmpl": os.path.join(output_dir, "%(uploader)s_%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": fmt,
        "http_headers": _HEADERS,
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts


# ─── TikTok fallback via tikwm.com API ────────────────────────────────────────

def _tikwm_download(url: str, output_dir: str) -> str:
    """
    Download a TikTok video via tikwm.com public API (no watermark).
    Returns the saved file path on success, raises on failure.
    """
    import json

    params = urlencode({"url": url, "hd": "1"})
    api_url = f"{_TIKWM_API}?{params}"

    req = urllib.request.Request(api_url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    if data.get("code") != 0:
        raise RuntimeError(f"tikwm API error: {data.get('msg', 'unknown')}")

    video_data = data["data"]
    video_url = video_data.get("play") or video_data.get("wmplay")
    if not video_url:
        raise RuntimeError("tikwm returned no playable URL")

    video_id = video_data.get("id", "unknown")
    author = video_data.get("author", {}).get("unique_id", "tiktok")
    filename = f"{author}_{video_id}.mp4"
    filepath = os.path.join(output_dir, filename)

    req2 = urllib.request.Request(video_url, headers=_HEADERS)
    with urllib.request.urlopen(req2, timeout=60) as resp2:
        with open(filepath, "wb") as f:
            f.write(resp2.read())

    if os.path.getsize(filepath) == 0:
        os.remove(filepath)
        raise RuntimeError("Downloaded file is empty")

    return filepath


# ─── Main download entry point ─────────────────────────────────────────────────

def download_video(
    job: DownloadJob,
    base_output: str,
    max_retries: int = 3,
    on_attempt: Optional[Callable[[int], None]] = None,
    cookies_browser: Optional[str] = None,
    use_cwd: bool = False,
) -> DownloadResult:
    """
    Download a single video with retry logic.
    TikTok/Douyin use tikwm.com API fallback when yt-dlp fails.
    use_cwd=True saves directly into base_output (no date subfolder).
    """
    output_dir = _build_output_dir(base_output, use_cwd)

    if job.platform in (Platform.TIKTOK, Platform.DOUYIN):
        return _download_with_tikwm(job, output_dir, max_retries, on_attempt)

    return _download_with_ytdlp(job, output_dir, max_retries, on_attempt, cookies_browser)


def _download_with_tikwm(
    job: DownloadJob,
    output_dir: str,
    max_retries: int,
    on_attempt: Optional[Callable[[int], None]],
) -> DownloadResult:
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        if on_attempt:
            on_attempt(attempt)
        try:
            filepath = _tikwm_download(job.url, output_dir)
            return DownloadResult(
                job=job,
                status=DownloadStatus.SUCCESS,
                output_path=filepath,
                attempts=attempt,
            )
        except Exception as exc:
            last_error = str(exc)

        if attempt < max_retries:
            time.sleep(2 ** attempt)

    return DownloadResult(
        job=job,
        status=DownloadStatus.FAILED,
        error=last_error,
        attempts=max_retries,
    )


def _download_with_ytdlp(
    job: DownloadJob,
    output_dir: str,
    max_retries: int,
    on_attempt: Optional[Callable[[int], None]],
    cookies_browser: Optional[str],
) -> DownloadResult:
    ydl_opts = _build_ydl_opts(output_dir, cookies_browser, platform=job.platform.value)
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        if on_attempt:
            on_attempt(attempt)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
                filepath = ydl.prepare_filename(info)

            return DownloadResult(
                job=job,
                status=DownloadStatus.SUCCESS,
                output_path=filepath,
                attempts=attempt,
            )
        except yt_dlp.utils.DownloadError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = f"Unexpected error: {exc}"

        if attempt < max_retries:
            time.sleep(2 ** attempt)

    return DownloadResult(
        job=job,
        status=DownloadStatus.FAILED,
        error=last_error,
        attempts=max_retries,
    )
