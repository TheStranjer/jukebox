"""Unit tests for YTDLPSource cookie handling."""

from __future__ import annotations

from jukebox import audio_source


class DummyYDL:
    """Test double for yt_dlp.YoutubeDL."""

    last_instance: "DummyYDL | None" = None

    def __init__(self, opts: dict[str, object]):
        self.opts = opts
        self.cookiejar = None
        DummyYDL.last_instance = self

    def __enter__(self) -> "DummyYDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict[str, object]:
        return {
            "url": "https://stream.example.com/audio",
            "webpage_url": url,
            "title": "Example",
            "duration": 120,
        }


def test_youtube_url_uses_env_cookiejar(monkeypatch) -> None:
    """YouTube URLs should attach cookies from YOUTUBE_COOKIES."""
    monkeypatch.setenv("YOUTUBE_COOKIES", "SID=abc; HSID=def")
    monkeypatch.setattr(audio_source.yt_dlp, "YoutubeDL", DummyYDL)

    source = audio_source.YTDLPSource()
    source.fetch_track("https://www.youtube.com/watch?v=123", "tester")

    cookiejar = DummyYDL.last_instance.cookiejar
    assert cookiejar is not None
    assert {cookie.name for cookie in cookiejar} == {"SID", "HSID"}


def test_non_youtube_url_ignores_env_cookiejar(monkeypatch) -> None:
    """Non-YouTube URLs should not attach YouTube cookies."""
    monkeypatch.setenv("YOUTUBE_COOKIES", "SID=abc")
    monkeypatch.setattr(audio_source.yt_dlp, "YoutubeDL", DummyYDL)

    source = audio_source.YTDLPSource()
    source.fetch_track("https://soundcloud.com/example", "tester")

    assert DummyYDL.last_instance.cookiejar is None


def test_youtube_url_loads_cookie_file(monkeypatch, tmp_path) -> None:
    """Cookie files should load into the cookie jar when provided."""
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("YOUTUBE_COOKIES", str(cookie_file))
    monkeypatch.setattr(audio_source.yt_dlp, "YoutubeDL", DummyYDL)

    source = audio_source.YTDLPSource()
    source.fetch_track("https://youtu.be/abc", "tester")

    cookiejar = DummyYDL.last_instance.cookiejar
    assert cookiejar is not None
    assert any(cookie.name == "SID" for cookie in cookiejar)
