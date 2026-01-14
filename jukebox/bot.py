"""Discord bot with slash commands for Jukebox."""

import asyncio
import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from .audio_source import AudioSource, YTDLPSource
from .database import set_language
from .i18n import get_available_locales, is_valid_locale, t, t_for
from .jukebox import Jukebox
from .track import Track


def _t(interaction: discord.Interaction, key: str, **kwargs: object) -> str:
    """Get a translated string for the interaction's user/guild context."""
    user_id = interaction.user.id
    guild_id = interaction.guild.id if interaction.guild else None
    return t_for(user_id, guild_id, key, **kwargs)

logger = logging.getLogger(__name__)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Reconnection settings
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_SECONDS = 2.0


class GuildState:
    """Per-guild state for the bot."""

    def __init__(self) -> None:
        self.jukebox = Jukebox()
        self.voice_client: discord.VoiceClient | None = None
        self.is_playing = False
        # Reconnection state
        self.target_channel_id: int | None = None
        self.intentional_disconnect = False
        self.reconnect_attempts = 0


class JukeboxBot(commands.Bot):
    """Discord bot for playing audio."""

    def __init__(self, audio_source: AudioSource | None = None):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.audio_source = audio_source or YTDLPSource()
        self.guild_states: dict[int, GuildState] = {}

    def get_guild_state(self, guild_id: int) -> GuildState:
        """Get or create state for a guild."""
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = GuildState()
        return self.guild_states[guild_id]

    async def setup_hook(self) -> None:
        """Set up the bot and sync commands."""
        await self.add_cog(JukeboxCog(self))
        await self.tree.sync()
        logger.info(t("log.slash_commands_synced"))

    async def on_ready(self) -> None:
        """Handle bot ready event."""
        logger.info(t("log.logged_in", user=self.user))


class JukeboxCog(commands.Cog):
    """Cog containing all Jukebox slash commands."""

    def __init__(self, bot: JukeboxBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state changes to detect disconnections."""
        state = self.bot.get_guild_state(member.guild.id)

        # Bot's own voice state changes
        if member.id == self.bot.user.id:  # type: ignore[union-attr]
            # Bot was disconnected from voice
            if before.channel is not None and after.channel is None:
                # If we were playing and it wasn't intentional, attempt reconnect
                if state.is_playing and not state.intentional_disconnect:
                    logger.info(
                        t("log.unexpected_disconnect", guild_id=member.guild.id)
                    )
                    await self._attempt_reconnect(member.guild.id)
            return

        voice_client = state.voice_client
        if voice_client is None or not voice_client.is_connected():
            return

        bot_channel = voice_client.channel
        if bot_channel is None:
            return

        if before.channel != bot_channel and after.channel != bot_channel:
            return

        if len(bot_channel.members) == 1 and bot_channel.members[0].id == self.bot.user.id:  # type: ignore[union-attr]
            await self._disconnect_from_voice(member.guild.id)

    async def _ensure_voice(
        self, interaction: discord.Interaction
    ) -> tuple[GuildState, discord.VoiceClient] | None:
        """Ensure the bot is in a voice channel.

        Returns the guild state and voice client, or None if failed.
        """
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return None

        member = cast(discord.Member, interaction.user)
        if member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(
                _t(interaction, "error.need_voice_channel"), ephemeral=True
            )
            return None

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.voice_client.is_connected():
            state.voice_client = await member.voice.channel.connect()
        elif state.voice_client.channel != member.voice.channel:
            await state.voice_client.move_to(member.voice.channel)

        # Track target channel for reconnection and reset reconnect state
        state.target_channel_id = member.voice.channel.id
        state.intentional_disconnect = False
        state.reconnect_attempts = 0

        return state, state.voice_client

    async def _disconnect_from_voice(self, guild_id: int) -> None:
        """Disconnect from voice and reset playback state."""
        state = self.bot.get_guild_state(guild_id)
        voice_client = state.voice_client

        if voice_client is None:
            return

        if not voice_client.is_connected():
            state.voice_client = None
            return

        state.intentional_disconnect = True
        state.target_channel_id = None
        state.is_playing = False
        state.jukebox.stop()
        await voice_client.disconnect()
        state.voice_client = None

    def _play_next(self, guild_id: int) -> None:
        """Callback to play the next track when current one finishes."""
        state = self.bot.get_guild_state(guild_id)

        if state.voice_client is None or not state.voice_client.is_connected():
            # Don't stop - attempt reconnection if not intentional
            if not state.intentional_disconnect and state.is_playing:
                asyncio.run_coroutine_threadsafe(
                    self._attempt_reconnect(guild_id), self.bot.loop
                )
            else:
                state.is_playing = False
            return

        next_track = state.jukebox.next()
        if next_track is None:
            state.is_playing = False
            if state.voice_client is not None and state.voice_client.is_connected():
                asyncio.run_coroutine_threadsafe(
                    self._disconnect_from_voice(guild_id), self.bot.loop
                )
            return

        self._play_track(state, next_track, guild_id)

    def _play_track(self, state: GuildState, track: Track, guild_id: int) -> None:
        """Play a track on the voice client."""
        if state.voice_client is None:
            return

        def after_playing(error: Exception | None) -> None:
            if error:
                logger.error(t("error.playback", error=error))
            # Schedule next track on the event loop
            asyncio.run_coroutine_threadsafe(
                self._async_play_next(guild_id), self.bot.loop
            )

        source = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
        state.voice_client.play(source, after=after_playing)
        state.is_playing = True

    async def _async_play_next(self, guild_id: int) -> None:
        """Async wrapper for playing next track."""
        self._play_next(guild_id)

    async def _attempt_reconnect(self, guild_id: int) -> bool:
        """Attempt to reconnect to voice channel after unexpected disconnect.

        Returns True if reconnection was successful.
        """
        state = self.bot.get_guild_state(guild_id)

        if state.intentional_disconnect:
            return False

        if state.target_channel_id is None:
            return False

        if state.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            logger.warning(t("log.reconnect_failed_max_attempts", guild_id=guild_id))
            state.is_playing = False
            return False

        state.reconnect_attempts += 1
        logger.info(
            t(
                "log.reconnecting",
                attempt=state.reconnect_attempts,
                max_attempts=MAX_RECONNECT_ATTEMPTS,
                guild_id=guild_id,
            )
        )

        try:
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return False

            channel = guild.get_channel(state.target_channel_id)
            if channel is None or not isinstance(channel, discord.VoiceChannel):
                return False

            state.voice_client = await channel.connect()
            state.reconnect_attempts = 0

            # Resume playback if we have a current track
            if state.jukebox.current is not None:
                logger.info(t("log.resuming_playback", guild_id=guild_id))
                self._play_track(state, state.jukebox.current, guild_id)
            return True

        except Exception as e:
            logger.error(t("log.reconnect_error", error=e, guild_id=guild_id))
            # Try again recursively
            return await self._attempt_reconnect(guild_id)

    @app_commands.command(name="play", description=t("command.play.description"))
    @app_commands.describe(url=t("command.play.url_description"))
    async def play(self, interaction: discord.Interaction, url: str) -> None:
        """Add a song to the queue and start playing."""
        result = await self._ensure_voice(interaction)
        if result is None:
            return

        state, voice_client = result
        guild_id = cast(discord.Guild, interaction.guild).id

        await interaction.response.defer()

        try:
            track = await asyncio.to_thread(
                self.bot.audio_source.fetch_track, url, interaction.user.display_name
            )
        except Exception as e:
            await interaction.followup.send(_t(interaction, "error.fetch_track", error=e))
            return

        position = state.jukebox.add(track)

        if not state.is_playing:
            next_track = state.jukebox.next()
            if next_track:
                self._play_track(state, next_track, guild_id)
                await interaction.followup.send(
                    _t(interaction, "response.now_playing", title=track.title, duration=track.format_duration())
                )
        else:
            await interaction.followup.send(
                _t(interaction, "response.added_to_queue", position=position + 1, title=track.title, duration=track.format_duration())
            )

    @app_commands.command(name="skip", description=t("command.skip.description"))
    async def skip(self, interaction: discord.Interaction) -> None:
        """Skip the current song."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.is_playing:
            await interaction.response.send_message(_t(interaction, "response.nothing_playing"), ephemeral=True)
            return

        current = state.jukebox.current
        state.voice_client.stop()  # This triggers the after callback
        await interaction.response.send_message(
            _t(interaction, "response.skipped_with_title", title=current.title) if current else _t(interaction, "response.skipped")
        )

    @app_commands.command(name="queue", description=t("command.queue.description"))
    async def queue(self, interaction: discord.Interaction) -> None:
        """Display the current queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.jukebox.is_empty and state.jukebox.current is None:
            await interaction.response.send_message(_t(interaction, "response.queue_empty"))
            return

        lines = []
        if state.jukebox.current:
            lines.append(
                _t(interaction, "response.queue_now_playing", title=state.jukebox.current.title, duration=state.jukebox.current.format_duration())
            )

        queue = state.jukebox.queue
        if queue:
            lines.append("\n" + _t(interaction, "response.queue_up_next"))
            for i, track in enumerate(queue[:10], 1):
                lines.append(_t(interaction, "response.queue_track_item", position=i, title=track.title, duration=track.format_duration()))
            if len(queue) > 10:
                lines.append(_t(interaction, "response.queue_more_tracks", count=len(queue) - 10))

            total_duration = state.jukebox.get_queue_duration()
            hours, remainder = divmod(total_duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                lines.append("\n" + _t(interaction, "response.queue_total_time_hours", hours=hours, minutes=minutes))
            else:
                lines.append("\n" + _t(interaction, "response.queue_total_time_minutes", minutes=minutes, seconds=seconds))

        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="clear", description=t("command.clear.description"))
    async def clear(self, interaction: discord.Interaction) -> None:
        """Clear all songs from the queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)
        count = state.jukebox.clear()
        await interaction.response.send_message(_t(interaction, "response.cleared_tracks", count=count))

    @app_commands.command(name="stop", description=t("command.stop.description"))
    async def stop(self, interaction: discord.Interaction) -> None:
        """Stop playback, clear queue, and disconnect from voice."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None:
            await interaction.response.send_message(_t(interaction, "response.not_connected"))
            return

        state.jukebox.clear()
        state.jukebox.stop()
        state.is_playing = False
        state.intentional_disconnect = True  # Prevent auto-reconnect
        state.target_channel_id = None
        await state.voice_client.disconnect()
        state.voice_client = None
        await interaction.response.send_message(_t(interaction, "response.stopped_disconnected"))

    @app_commands.command(name="pause", description=t("command.pause.description"))
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pause playback."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.voice_client.is_playing():
            await interaction.response.send_message(_t(interaction, "response.nothing_playing"), ephemeral=True)
            return

        state.voice_client.pause()
        await interaction.response.send_message(_t(interaction, "response.paused"))

    @app_commands.command(name="resume", description=t("command.resume.description"))
    async def resume(self, interaction: discord.Interaction) -> None:
        """Resume playback."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.voice_client.is_paused():
            await interaction.response.send_message(_t(interaction, "response.nothing_paused"), ephemeral=True)
            return

        state.voice_client.resume()
        await interaction.response.send_message(_t(interaction, "response.resumed"))

    @app_commands.command(name="nowplaying", description=t("command.nowplaying.description"))
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        """Show what's currently playing."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)
        current = state.jukebox.current

        if current is None:
            await interaction.response.send_message(_t(interaction, "response.nothing_playing"))
            return

        await interaction.response.send_message(
            _t(interaction, "response.nowplaying_detail", title=current.title, duration=current.format_duration(), requester=current.requester)
        )

    @app_commands.command(name="shuffle", description=t("command.shuffle.description"))
    async def shuffle(self, interaction: discord.Interaction) -> None:
        """Shuffle the queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if len(state.jukebox.queue) < 2:
            await interaction.response.send_message(
                _t(interaction, "response.not_enough_tracks_shuffle"), ephemeral=True
            )
            return

        state.jukebox.shuffle()
        await interaction.response.send_message(_t(interaction, "response.queue_shuffled"))

    @app_commands.command(name="remove", description=t("command.remove.description"))
    @app_commands.describe(position=t("command.remove.position_description"))
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        """Remove a song from the queue by position."""
        if interaction.guild is None:
            await interaction.response.send_message(
                _t(interaction, "error.server_only_command"), ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        try:
            track = state.jukebox.remove(position - 1)
            await interaction.response.send_message(
                _t(interaction, "response.removed_track", title=track.title, position=position)
            )
        except IndexError:
            await interaction.response.send_message(
                _t(interaction, "response.invalid_position", count=len(state.jukebox.queue)),
                ephemeral=True,
            )

    @app_commands.command(name="language", description=t("command.language.description"))
    @app_commands.describe(
        language=t("command.language.language_description"),
        personal=t("command.language.personal_description"),
    )
    async def language(
        self, interaction: discord.Interaction, language: str, personal: bool
    ) -> None:
        """Set the language for the bot."""
        # Validate the language code
        if not is_valid_locale(language):
            available = ", ".join(get_available_locales())
            await interaction.response.send_message(
                _t(interaction, "response.invalid_language", languages=available),
                ephemeral=True,
            )
            return

        if personal:
            # Set personal language for the user
            set_language("user", interaction.user.id, language)
            # Use the NEW language for the response
            await interaction.response.send_message(
                t_for(interaction.user.id, None, "response.language_set_personal", language=language),
                ephemeral=True,
            )
        else:
            # Set language for the entire guild
            if interaction.guild is None:
                await interaction.response.send_message(
                    _t(interaction, "error.server_only_command"), ephemeral=True
                )
                return

            # Check if user has permission to manage the guild
            member = cast(discord.Member, interaction.user)
            if not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    _t(interaction, "response.need_manage_guild"), ephemeral=True
                )
                return

            set_language("guild", interaction.guild.id, language)
            # Use the NEW language for the response
            await interaction.response.send_message(
                t_for(interaction.user.id, interaction.guild.id, "response.language_set_guild", language=language)
            )
