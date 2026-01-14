"""Audio source protocol and implementations."""

import http.cookiejar
import os
from http.cookies import SimpleCookie
from typing import Protocol
from urllib.parse import urlparse

import yt_dlp
from yt_dlp import cookies as ytdlp_cookies

from .i18n import t
from .track import Track


class AudioSource(Protocol):
    """Protocol for fetching audio track information."""

    def fetch_track(self, url: str, requester: str) -> Track:
        """Fetch track information from a URL.

        Args:
            url: The URL to fetch audio from.
            requester: The Discord user who requested the track.

        Returns:
            A Track object with metadata and stream URL.
        """
        ...


class YTDLPSource:
    """Audio source implementation using yt-dlp."""

    YTDLP_OPTIONS = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    @staticmethod
    def _is_youtube_url(url: str) -> bool:
        hostname = (urlparse(url).hostname or "").lower()
        return (
            hostname == "youtu.be"
            or hostname == "youtube.com"
            or hostname.endswith(".youtube.com")
            or hostname == "youtube-nocookie.com"
            or hostname.endswith(".youtube-nocookie.com")
        )

    @staticmethod
    def _cookie_domain_for_url(url: str) -> str:
        hostname = (urlparse(url).hostname or "").lower()
        if hostname == "youtu.be":
            return ".youtu.be"
        if hostname.endswith("youtube-nocookie.com"):
            return ".youtube-nocookie.com"
        return ".youtube.com"

    @staticmethod
    def _cookiejar_from_env(url: str) -> ytdlp_cookies.YoutubeDLCookieJar | None:
        raw_cookies = os.getenv("YOUTUBE_COOKIES")
        if not raw_cookies:
            return None

        if os.path.exists(raw_cookies):
            cookiejar = ytdlp_cookies.YoutubeDLCookieJar(raw_cookies)
            cookiejar.load(raw_cookies, ignore_discard=True, ignore_expires=True)
            return cookiejar

        cookie = SimpleCookie()
        cookie.load(raw_cookies)
        cookiejar = ytdlp_cookies.YoutubeDLCookieJar()
        domain = YTDLPSource._cookie_domain_for_url(url)
        for morsel in cookie.values():
            if not morsel.key:
                continue
            cookiejar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=morsel.key,
                    value=morsel.value,
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=True,
                    domain_initial_dot=domain.startswith("."),
                    path="/",
                    path_specified=True,
                    secure=False,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
            )
        return cookiejar

    def fetch_track(self, url: str, requester: str) -> Track:
        """Fetch track information using yt-dlp.

        Args:
            url: The URL to fetch audio from (YouTube, SoundCloud, etc.).
            requester: The Discord user who requested the track.

        Returns:
            A Track object with metadata and stream URL.

        Raises:
            Exception: If the URL cannot be processed.
        """
        with yt_dlp.YoutubeDL(self.YTDLP_OPTIONS) as ydl:
            if self._is_youtube_url(url):
                cookiejar = self._cookiejar_from_env(url)
                if cookiejar is not None:
                    ydl.cookiejar = cookiejar
            info = ydl.extract_info(url, download=False)

            if info is None:
                raise ValueError(t("error.extract_info", url=url))

            # Get the best audio format URL
            stream_url = info.get("url", "")
            if not stream_url and "formats" in info:
                # Find the best audio format
                for fmt in reversed(info["formats"]):
                    if fmt.get("acodec") != "none":
                        stream_url = fmt.get("url", "")
                        break

            return Track(
                url=info.get("webpage_url", url),
                title=info.get("title", t("track.unknown_title")),
                duration=info.get("duration", 0) or 0,
                requester=requester,
                stream_url=stream_url,
            )
