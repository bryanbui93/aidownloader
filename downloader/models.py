from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    TIKTOK = "TikTok"
    DOUYIN = "Douyin"
    FACEBOOK = "Facebook"
    YOUTUBE = "YouTube"
    UNKNOWN = "Unknown"


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DownloadJob:
    url: str
    platform: Platform = Platform.UNKNOWN
    row_number: int = 0

    def __post_init__(self):
        self.platform = detect_platform(self.url)


@dataclass
class DownloadResult:
    job: DownloadJob
    status: DownloadStatus
    output_path: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0


def detect_platform(url: str) -> Platform:
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return Platform.TIKTOK
    if "douyin.com" in url_lower:
        return Platform.DOUYIN
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return Platform.FACEBOOK
    if "youtube.com/shorts" in url_lower or "youtu.be" in url_lower:
        return Platform.YOUTUBE
    return Platform.UNKNOWN
