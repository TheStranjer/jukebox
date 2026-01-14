"""Jukebox class - core business logic for queue management."""

import random
from typing import Callable

from .i18n import t
from .track import Track


class Jukebox:
    """Manages the audio queue and playback state.

    This class contains pure business logic with no I/O dependencies,
    making it easily unit testable.
    """

    def __init__(self, on_track_change: Callable[[Track | None], None] | None = None):
        """Initialize the Jukebox.

        Args:
            on_track_change: Optional callback invoked when the current track changes.
        """
        self._queue: list[Track] = []
        self._current: Track | None = None
        self._history: list[Track] = []
        self._on_track_change = on_track_change

    @property
    def current(self) -> Track | None:
        """Get the currently playing track."""
        return self._current

    @property
    def queue(self) -> list[Track]:
        """Get a copy of the current queue."""
        return self._queue.copy()

    @property
    def history(self) -> list[Track]:
        """Get a copy of the play history."""
        return self._history.copy()

    @property
    def is_empty(self) -> bool:
        """Check if the queue is empty and nothing is playing."""
        return self._current is None and len(self._queue) == 0

    def add(self, track: Track) -> int:
        """Add a track to the queue.

        Args:
            track: The track to add.

        Returns:
            The position in the queue (0-indexed).
        """
        self._queue.append(track)
        return len(self._queue) - 1

    def add_next(self, track: Track) -> None:
        """Add a track to play next (front of queue).

        Args:
            track: The track to add.
        """
        self._queue.insert(0, track)

    def remove(self, index: int) -> Track:
        """Remove a track from the queue by index.

        Args:
            index: The index of the track to remove (0-indexed).

        Returns:
            The removed track.

        Raises:
            IndexError: If the index is out of range.
        """
        if index < 0 or index >= len(self._queue):
            raise IndexError(t("error.index_out_of_range", index=index, size=len(self._queue)))
        return self._queue.pop(index)

    def clear(self) -> int:
        """Clear all tracks from the queue.

        Returns:
            The number of tracks that were cleared.
        """
        count = len(self._queue)
        self._queue.clear()
        return count

    def shuffle(self) -> None:
        """Shuffle the queue randomly."""
        random.shuffle(self._queue)

    def next(self) -> Track | None:
        """Advance to the next track in the queue.

        Moves the current track to history and pops the next from the queue.

        Returns:
            The new current track, or None if the queue is empty.
        """
        if self._current is not None:
            self._history.append(self._current)

        if self._queue:
            self._current = self._queue.pop(0)
        else:
            self._current = None

        if self._on_track_change:
            self._on_track_change(self._current)

        return self._current

    def skip(self) -> Track | None:
        """Skip the current track and play the next one.

        This is an alias for next() with clearer intent.

        Returns:
            The new current track, or None if the queue is empty.
        """
        return self.next()

    def stop(self) -> None:
        """Stop playback and clear the current track.

        Does not clear the queue.
        """
        if self._current is not None:
            self._history.append(self._current)
            self._current = None

        if self._on_track_change:
            self._on_track_change(None)

    def start(self) -> Track | None:
        """Start playing from the queue if not already playing.

        Returns:
            The current track if already playing, or the next track from queue.
        """
        if self._current is not None:
            return self._current
        return self.next()

    def move(self, from_index: int, to_index: int) -> None:
        """Move a track from one position to another in the queue.

        Args:
            from_index: The current index of the track.
            to_index: The desired index for the track.

        Raises:
            IndexError: If either index is out of range.
        """
        if from_index < 0 or from_index >= len(self._queue):
            raise IndexError(t("error.from_index_out_of_range", index=from_index))
        if to_index < 0 or to_index >= len(self._queue):
            raise IndexError(t("error.to_index_out_of_range", index=to_index))

        track = self._queue.pop(from_index)
        self._queue.insert(to_index, track)

    def get_queue_duration(self) -> int:
        """Get the total duration of all tracks in the queue.

        Returns:
            Total duration in seconds.
        """
        return sum(track.duration for track in self._queue)

    def clear_history(self) -> None:
        """Clear the play history."""
        self._history.clear()
