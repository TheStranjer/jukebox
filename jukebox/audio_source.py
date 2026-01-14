"""Audio source protocol and implementations."""

from typing import Protocol

import yt_dlp

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
            info = ydl.extract_info(url, download=False)

            if info is None:
                raise ValueError(f"Could not extract info from URL: {url}")

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
                title=info.get("title", "Unknown"),
                duration=info.get("duration", 0) or 0,
                requester=requester,
                stream_url=stream_url,
            )
