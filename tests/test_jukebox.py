"""Unit tests for Jukebox class."""

import pytest

from jukebox.jukebox import Jukebox
from jukebox.track import Track


def make_track(title: str = "Test", duration: int = 180) -> Track:
    """Create a test track with sensible defaults."""
    return Track(
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        title=title,
        duration=duration,
        requester="TestUser",
    )


class TestJukeboxQueue:
    """Tests for queue operations."""

    def test_add_track(self) -> None:
        """Test adding a track to the queue."""
        jukebox = Jukebox()
        track = make_track("Song 1")

        position = jukebox.add(track)

        assert position == 0
        assert len(jukebox.queue) == 1
        assert jukebox.queue[0] == track

    def test_add_multiple_tracks(self) -> None:
        """Test adding multiple tracks to the queue."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")
        track3 = make_track("Song 3")

        pos1 = jukebox.add(track1)
        pos2 = jukebox.add(track2)
        pos3 = jukebox.add(track3)

        assert pos1 == 0
        assert pos2 == 1
        assert pos3 == 2
        assert len(jukebox.queue) == 3

    def test_add_next(self) -> None:
        """Test adding a track to play next."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")
        track_next = make_track("Play Next")

        jukebox.add(track1)
        jukebox.add(track2)
        jukebox.add_next(track_next)

        assert jukebox.queue[0] == track_next
        assert jukebox.queue[1] == track1
        assert jukebox.queue[2] == track2

    def test_remove_track(self) -> None:
        """Test removing a track from the queue."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")
        track3 = make_track("Song 3")

        jukebox.add(track1)
        jukebox.add(track2)
        jukebox.add(track3)

        removed = jukebox.remove(1)

        assert removed == track2
        assert len(jukebox.queue) == 2
        assert jukebox.queue[0] == track1
        assert jukebox.queue[1] == track3

    def test_remove_invalid_index(self) -> None:
        """Test removing with an invalid index raises error."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))

        with pytest.raises(IndexError):
            jukebox.remove(5)

    def test_remove_negative_index(self) -> None:
        """Test removing with a negative index raises error."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))

        with pytest.raises(IndexError):
            jukebox.remove(-1)

    def test_clear_queue(self) -> None:
        """Test clearing the queue."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))
        jukebox.add(make_track("Song 2"))
        jukebox.add(make_track("Song 3"))

        count = jukebox.clear()

        assert count == 3
        assert len(jukebox.queue) == 0

    def test_clear_empty_queue(self) -> None:
        """Test clearing an already empty queue."""
        jukebox = Jukebox()

        count = jukebox.clear()

        assert count == 0

    def test_shuffle_queue(self) -> None:
        """Test shuffling the queue changes order."""
        jukebox = Jukebox()
        tracks = [make_track(f"Song {i}") for i in range(20)]
        for track in tracks:
            jukebox.add(track)

        original_order = jukebox.queue.copy()
        jukebox.shuffle()

        # With 20 tracks, probability of same order is ~1/20!
        assert jukebox.queue != original_order
        assert set(t.title for t in jukebox.queue) == set(t.title for t in original_order)

    def test_queue_returns_copy(self) -> None:
        """Test that queue property returns a copy."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))

        queue_copy = jukebox.queue
        queue_copy.append(make_track("Song 2"))

        assert len(jukebox.queue) == 1


class TestJukeboxPlayback:
    """Tests for playback control."""

    def test_next_track(self) -> None:
        """Test advancing to the next track."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")

        jukebox.add(track1)
        jukebox.add(track2)

        current = jukebox.next()

        assert current == track1
        assert jukebox.current == track1
        assert len(jukebox.queue) == 1

    def test_next_track_empty_queue(self) -> None:
        """Test next() with empty queue returns None."""
        jukebox = Jukebox()

        current = jukebox.next()

        assert current is None
        assert jukebox.current is None

    def test_next_moves_to_history(self) -> None:
        """Test that next() moves current track to history."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")

        jukebox.add(track1)
        jukebox.add(track2)

        jukebox.next()  # Now playing track1
        jukebox.next()  # Now playing track2, track1 in history

        assert len(jukebox.history) == 1
        assert jukebox.history[0] == track1
        assert jukebox.current == track2

    def test_skip_is_alias_for_next(self) -> None:
        """Test that skip() behaves like next()."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")

        jukebox.add(track1)
        jukebox.add(track2)

        jukebox.next()  # Start playing track1
        current = jukebox.skip()  # Skip to track2

        assert current == track2
        assert jukebox.current == track2
        assert len(jukebox.history) == 1

    def test_stop_clears_current(self) -> None:
        """Test that stop() clears current track."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")

        jukebox.add(track1)
        jukebox.add(track2)
        jukebox.next()  # Start playing

        jukebox.stop()

        assert jukebox.current is None
        assert len(jukebox.queue) == 1  # Queue not cleared
        assert len(jukebox.history) == 1

    def test_stop_when_nothing_playing(self) -> None:
        """Test stop() when nothing is playing."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))

        jukebox.stop()  # Should not raise

        assert jukebox.current is None
        assert len(jukebox.queue) == 1

    def test_start_when_not_playing(self) -> None:
        """Test start() begins playback."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        jukebox.add(track1)

        current = jukebox.start()

        assert current == track1
        assert jukebox.current == track1

    def test_start_when_already_playing(self) -> None:
        """Test start() returns current if already playing."""
        jukebox = Jukebox()
        track1 = make_track("Song 1")
        track2 = make_track("Song 2")

        jukebox.add(track1)
        jukebox.add(track2)
        jukebox.next()  # Start playing track1

        current = jukebox.start()

        assert current == track1
        assert len(jukebox.queue) == 1

    def test_is_empty(self) -> None:
        """Test is_empty property."""
        jukebox = Jukebox()

        assert jukebox.is_empty is True

        jukebox.add(make_track("Song 1"))
        assert jukebox.is_empty is False

        jukebox.next()  # Now playing
        assert jukebox.is_empty is False

        jukebox.stop()
        assert jukebox.is_empty is True


class TestJukeboxMove:
    """Tests for moving tracks in queue."""

    def test_move_track_forward(self) -> None:
        """Test moving a track forward in the queue."""
        jukebox = Jukebox()
        tracks = [make_track(f"Song {i}") for i in range(5)]
        for track in tracks:
            jukebox.add(track)

        jukebox.move(0, 3)

        assert jukebox.queue[0].title == "Song 1"
        assert jukebox.queue[3].title == "Song 0"

    def test_move_track_backward(self) -> None:
        """Test moving a track backward in the queue."""
        jukebox = Jukebox()
        tracks = [make_track(f"Song {i}") for i in range(5)]
        for track in tracks:
            jukebox.add(track)

        jukebox.move(4, 1)

        assert jukebox.queue[1].title == "Song 4"
        assert jukebox.queue[4].title == "Song 3"

    def test_move_invalid_from_index(self) -> None:
        """Test move with invalid from_index raises error."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))

        with pytest.raises(IndexError):
            jukebox.move(5, 0)

    def test_move_invalid_to_index(self) -> None:
        """Test move with invalid to_index raises error."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))

        with pytest.raises(IndexError):
            jukebox.move(0, 5)


class TestJukeboxDuration:
    """Tests for duration calculations."""

    def test_get_queue_duration(self) -> None:
        """Test calculating total queue duration."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1", duration=180))
        jukebox.add(make_track("Song 2", duration=240))
        jukebox.add(make_track("Song 3", duration=120))

        total = jukebox.get_queue_duration()

        assert total == 540

    def test_get_queue_duration_empty(self) -> None:
        """Test queue duration for empty queue."""
        jukebox = Jukebox()

        total = jukebox.get_queue_duration()

        assert total == 0


class TestJukeboxHistory:
    """Tests for history functionality."""

    def test_history_accumulates(self) -> None:
        """Test that history accumulates played tracks."""
        jukebox = Jukebox()
        tracks = [make_track(f"Song {i}") for i in range(3)]
        for track in tracks:
            jukebox.add(track)

        jukebox.next()  # Play Song 0
        jukebox.next()  # Play Song 1, Song 0 to history
        jukebox.next()  # Play Song 2, Song 1 to history

        assert len(jukebox.history) == 2
        assert jukebox.history[0].title == "Song 0"
        assert jukebox.history[1].title == "Song 1"

    def test_clear_history(self) -> None:
        """Test clearing play history."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))
        jukebox.add(make_track("Song 2"))
        jukebox.next()
        jukebox.next()

        jukebox.clear_history()

        assert len(jukebox.history) == 0

    def test_history_returns_copy(self) -> None:
        """Test that history property returns a copy."""
        jukebox = Jukebox()
        jukebox.add(make_track("Song 1"))
        jukebox.next()
        jukebox.stop()

        history_copy = jukebox.history
        history_copy.append(make_track("Fake"))

        assert len(jukebox.history) == 1


class TestJukeboxCallback:
    """Tests for track change callback."""

    def test_callback_on_next(self) -> None:
        """Test callback is invoked when track changes."""
        changes: list[Track | None] = []
        jukebox = Jukebox(on_track_change=lambda t: changes.append(t))

        track1 = make_track("Song 1")
        track2 = make_track("Song 2")
        jukebox.add(track1)
        jukebox.add(track2)

        jukebox.next()
        jukebox.next()
        jukebox.next()  # Queue empty

        assert len(changes) == 3
        assert changes[0] == track1
        assert changes[1] == track2
        assert changes[2] is None

    def test_callback_on_stop(self) -> None:
        """Test callback is invoked on stop."""
        changes: list[Track | None] = []
        jukebox = Jukebox(on_track_change=lambda t: changes.append(t))

        jukebox.add(make_track("Song 1"))
        jukebox.next()
        jukebox.stop()

        assert len(changes) == 2
        assert changes[1] is None
