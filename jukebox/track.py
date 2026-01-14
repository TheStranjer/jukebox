"""Track dataclass representing an audio track."""

from dataclasses import dataclass


@dataclass
class Track:
    """Represents an audio track in the queue."""

    url: str
    title: str
    duration: int  # Duration in seconds
    requester: str  # Discord user who requested the track
    stream_url: str = ""  # URL for streaming audio (populated by AudioSource)

    def format_duration(self) -> str:
        """Format duration as MM:SS or HH:MM:SS."""
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
