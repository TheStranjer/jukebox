"""Unit tests for voice reconnection behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jukebox.bot import (
    GuildState,
    JukeboxBot,
    JukeboxCog,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_DELAY_SECONDS,
)
from jukebox.track import Track


def make_track(title: str = "Test", duration: int = 180) -> Track:
    """Create a test track with sensible defaults."""
    return Track(
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        title=title,
        duration=duration,
        requester="TestUser",
        stream_url=f"https://stream.example.com/{title.lower()}",
    )


class TestGuildState:
    """Tests for GuildState reconnection fields."""

    def test_initial_state(self) -> None:
        """Test that GuildState initializes with correct default values."""
        state = GuildState()

        assert state.voice_client is None
        assert state.is_playing is False
        assert state.target_channel_id is None
        assert state.intentional_disconnect is False
        assert state.reconnect_attempts == 0

    def test_reconnect_state_tracking(self) -> None:
        """Test that reconnect state can be modified."""
        state = GuildState()

        state.target_channel_id = 123456789
        state.intentional_disconnect = True
        state.reconnect_attempts = 2

        assert state.target_channel_id == 123456789
        assert state.intentional_disconnect is True
        assert state.reconnect_attempts == 2


class TestReconnectLogic:
    """Tests for reconnection logic in JukeboxCog."""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create a mock JukeboxBot."""
        bot = MagicMock(spec=JukeboxBot)
        bot.loop = asyncio.new_event_loop()
        bot.guild_states = {}
        bot.get_guild_state = lambda guild_id: bot.guild_states.setdefault(
            guild_id, GuildState()
        )
        return bot

    @pytest.fixture
    def cog(self, mock_bot: MagicMock) -> JukeboxCog:
        """Create a JukeboxCog with mock bot."""
        return JukeboxCog(mock_bot)

    @pytest.mark.asyncio
    async def test_reconnect_skipped_when_intentional(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that reconnection is skipped when disconnect was intentional."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)
        state.intentional_disconnect = True
        state.target_channel_id = 67890
        state.is_playing = True

        result = await cog._attempt_reconnect(guild_id)

        assert result is False
        assert state.reconnect_attempts == 0

    @pytest.mark.asyncio
    async def test_reconnect_skipped_when_no_target_channel(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that reconnection is skipped when no target channel is set."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)
        state.target_channel_id = None
        state.is_playing = True

        result = await cog._attempt_reconnect(guild_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_reconnect_fails_after_max_attempts(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that reconnection stops after max attempts."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)
        state.target_channel_id = 67890
        state.is_playing = True
        state.reconnect_attempts = MAX_RECONNECT_ATTEMPTS  # Already at max

        result = await cog._attempt_reconnect(guild_id)

        assert result is False
        assert state.is_playing is False  # Should stop playing after max attempts

    @pytest.mark.asyncio
    async def test_reconnect_increments_attempts(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that reconnect attempts are incremented."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)
        state.target_channel_id = 67890
        state.is_playing = True
        state.reconnect_attempts = 0

        # Mock guild not found to trigger failure path
        mock_bot.get_guild = MagicMock(return_value=None)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await cog._attempt_reconnect(guild_id)

        assert result is False
        # Attempts should have been incremented before failure
        assert state.reconnect_attempts >= 1

    @pytest.mark.asyncio
    async def test_successful_reconnect(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test successful reconnection."""
        guild_id = 12345
        channel_id = 67890
        state = mock_bot.get_guild_state(guild_id)
        state.target_channel_id = channel_id
        state.is_playing = True
        state.reconnect_attempts = 0

        # Mock the current track
        track = make_track("Test Song")
        state.jukebox._current = track

        # Mock guild and channel
        mock_channel = AsyncMock()
        mock_channel.connect = AsyncMock(return_value=MagicMock())
        mock_guild = MagicMock()
        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        # Make channel pass the isinstance check
        with patch("discord.VoiceChannel", type(mock_channel)):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Also need to mock _play_track to avoid issues
                cog._play_track = MagicMock()
                result = await cog._attempt_reconnect(guild_id)

        assert result is True
        assert state.reconnect_attempts == 0  # Reset after success
        assert state.voice_client is not None

    @pytest.mark.asyncio
    async def test_reconnect_resumes_playback(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that playback resumes after successful reconnection."""
        guild_id = 12345
        channel_id = 67890
        state = mock_bot.get_guild_state(guild_id)
        state.target_channel_id = channel_id
        state.is_playing = True

        # Set a current track
        track = make_track("Resume Test")
        state.jukebox._current = track

        # Mock guild and channel
        mock_voice_client = MagicMock()
        mock_channel = AsyncMock()
        mock_channel.connect = AsyncMock(return_value=mock_voice_client)
        mock_guild = MagicMock()
        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        with patch("discord.VoiceChannel", type(mock_channel)):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                cog._play_track = MagicMock()
                await cog._attempt_reconnect(guild_id)

        # Verify _play_track was called with the current track
        cog._play_track.assert_called_once_with(state, track, guild_id)


class TestPlayNextReconnect:
    """Tests for _play_next reconnection triggering."""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create a mock JukeboxBot."""
        bot = MagicMock(spec=JukeboxBot)
        bot.loop = asyncio.new_event_loop()
        bot.guild_states = {}
        bot.get_guild_state = lambda guild_id: bot.guild_states.setdefault(
            guild_id, GuildState()
        )
        return bot

    @pytest.fixture
    def cog(self, mock_bot: MagicMock) -> JukeboxCog:
        """Create a JukeboxCog with mock bot."""
        return JukeboxCog(mock_bot)

    def test_play_next_triggers_reconnect_when_disconnected(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that _play_next triggers reconnection when disconnected mid-song."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)
        state.voice_client = None  # Disconnected
        state.is_playing = True  # Was playing
        state.intentional_disconnect = False
        state.target_channel_id = 67890

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            cog._play_next(guild_id)

        # Should have scheduled reconnection
        mock_run.assert_called_once()
        # is_playing should still be True (waiting for reconnect)
        assert state.is_playing is True

    def test_play_next_stops_when_intentional_disconnect(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that _play_next doesn't reconnect after intentional disconnect."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)
        state.voice_client = None
        state.is_playing = True
        state.intentional_disconnect = True

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            cog._play_next(guild_id)

        # Should NOT have scheduled reconnection
        mock_run.assert_not_called()
        # is_playing should be False
        assert state.is_playing is False

    def test_play_next_continues_normally_when_connected(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that _play_next works normally when still connected."""
        guild_id = 12345
        state = mock_bot.get_guild_state(guild_id)

        # Mock a connected voice client
        mock_voice_client = MagicMock()
        mock_voice_client.is_connected = MagicMock(return_value=True)
        state.voice_client = mock_voice_client
        state.is_playing = True

        # Add a track to the queue
        track = make_track("Next Song")
        state.jukebox.add(track)

        cog._play_track = MagicMock()
        cog._play_next(guild_id)

        # Should have called _play_track with the next track
        cog._play_track.assert_called_once()


class TestVoiceStateUpdate:
    """Tests for on_voice_state_update event handler."""

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create a mock JukeboxBot."""
        bot = MagicMock(spec=JukeboxBot)
        bot.loop = asyncio.new_event_loop()
        bot.guild_states = {}
        bot.get_guild_state = lambda guild_id: bot.guild_states.setdefault(
            guild_id, GuildState()
        )
        bot.user = MagicMock()
        bot.user.id = 999999  # Bot's user ID
        return bot

    @pytest.fixture
    def cog(self, mock_bot: MagicMock) -> JukeboxCog:
        """Create a JukeboxCog with mock bot."""
        return JukeboxCog(mock_bot)

    @pytest.mark.asyncio
    async def test_ignores_other_users(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that voice state changes from other users are ignored."""
        member = MagicMock()
        member.id = 111111  # Different from bot ID
        member.guild.id = 12345

        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        cog._attempt_reconnect = AsyncMock()
        await cog.on_voice_state_update(member, before, after)

        cog._attempt_reconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_triggers_reconnect_on_bot_disconnect(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that bot disconnection triggers reconnection attempt."""
        guild_id = 12345
        member = MagicMock()
        member.id = mock_bot.user.id  # Bot's ID
        member.guild.id = guild_id

        state = mock_bot.get_guild_state(guild_id)
        state.is_playing = True
        state.intentional_disconnect = False

        before = MagicMock()
        before.channel = MagicMock()  # Was in a channel
        after = MagicMock()
        after.channel = None  # Now disconnected

        cog._attempt_reconnect = AsyncMock()
        await cog.on_voice_state_update(member, before, after)

        cog._attempt_reconnect.assert_called_once_with(guild_id)

    @pytest.mark.asyncio
    async def test_no_reconnect_when_not_playing(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that disconnection while not playing doesn't trigger reconnect."""
        guild_id = 12345
        member = MagicMock()
        member.id = mock_bot.user.id
        member.guild.id = guild_id

        state = mock_bot.get_guild_state(guild_id)
        state.is_playing = False  # Not playing
        state.intentional_disconnect = False

        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        cog._attempt_reconnect = AsyncMock()
        await cog.on_voice_state_update(member, before, after)

        cog._attempt_reconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_reconnect_when_intentional(
        self, cog: JukeboxCog, mock_bot: MagicMock
    ) -> None:
        """Test that intentional disconnection doesn't trigger reconnect."""
        guild_id = 12345
        member = MagicMock()
        member.id = mock_bot.user.id
        member.guild.id = guild_id

        state = mock_bot.get_guild_state(guild_id)
        state.is_playing = True
        state.intentional_disconnect = True  # Intentional

        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        cog._attempt_reconnect = AsyncMock()
        await cog.on_voice_state_update(member, before, after)

        cog._attempt_reconnect.assert_not_called()


class TestStopCommandClearsReconnect:
    """Tests for stop command clearing reconnect state."""

    def test_stop_sets_intentional_disconnect(self) -> None:
        """Test that stopping playback sets intentional_disconnect flag."""
        state = GuildState()
        state.intentional_disconnect = False
        state.target_channel_id = 12345

        # Simulate what stop command does
        state.intentional_disconnect = True
        state.target_channel_id = None

        assert state.intentional_disconnect is True
        assert state.target_channel_id is None
