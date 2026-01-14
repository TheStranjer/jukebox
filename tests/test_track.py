"""Unit tests for Track dataclass."""

import pytest

from jukebox.track import Track


class TestTrack:
    """Tests for Track dataclass."""

    def test_create_track(self) -> None:
        """Test creating a track with all fields."""
        track = Track(
            url="https://youtube.com/watch?v=123",
            title="Test Song",
            duration=180,
            requester="TestUser",
            stream_url="https://stream.example.com/audio.mp3",
        )

        assert track.url == "https://youtube.com/watch?v=123"
        assert track.title == "Test Song"
        assert track.duration == 180
        assert track.requester == "TestUser"
        assert track.stream_url == "https://stream.example.com/audio.mp3"

    def test_create_track_default_stream_url(self) -> None:
        """Test creating a track without stream_url uses default."""
        track = Track(
            url="https://youtube.com/watch?v=123",
            title="Test Song",
            duration=180,
            requester="TestUser",
        )

        assert track.stream_url == ""

    def test_format_duration_minutes_only(self) -> None:
        """Test duration formatting for tracks under an hour."""
        track = Track(
            url="https://example.com",
            title="Short Song",
            duration=185,  # 3:05
            requester="User",
        )

        assert track.format_duration() == "3:05"

    def test_format_duration_with_hours(self) -> None:
        """Test duration formatting for tracks over an hour."""
        track = Track(
            url="https://example.com",
            title="Long Song",
            duration=3725,  # 1:02:05
            requester="User",
        )

        assert track.format_duration() == "1:02:05"

    def test_format_duration_zero(self) -> None:
        """Test duration formatting for zero duration."""
        track = Track(
            url="https://example.com",
            title="Unknown Duration",
            duration=0,
            requester="User",
        )

        assert track.format_duration() == "0:00"

    def test_format_duration_exact_hour(self) -> None:
        """Test duration formatting for exactly one hour."""
        track = Track(
            url="https://example.com",
            title="Hour Song",
            duration=3600,  # 1:00:00
            requester="User",
        )

        assert track.format_duration() == "1:00:00"
