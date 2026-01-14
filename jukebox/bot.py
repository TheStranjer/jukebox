"""Discord bot with slash commands for Jukebox."""

import asyncio
import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from .audio_source import AudioSource, YTDLPSource
from .jukebox import Jukebox
from .track import Track

logger = logging.getLogger(__name__)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class GuildState:
    """Per-guild state for the bot."""

    def __init__(self) -> None:
        self.jukebox = Jukebox()
        self.voice_client: discord.VoiceClient | None = None
        self.is_playing = False


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
        logger.info("Slash commands synced")

    async def on_ready(self) -> None:
        """Handle bot ready event."""
        logger.info(f"Logged in as {self.user}")


class JukeboxCog(commands.Cog):
    """Cog containing all Jukebox slash commands."""

    def __init__(self, bot: JukeboxBot):
        self.bot = bot

    async def _ensure_voice(
        self, interaction: discord.Interaction
    ) -> tuple[GuildState, discord.VoiceClient] | None:
        """Ensure the bot is in a voice channel.

        Returns the guild state and voice client, or None if failed.
        """
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return None

        member = cast(discord.Member, interaction.user)
        if member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(
                "You need to be in a voice channel.", ephemeral=True
            )
            return None

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.voice_client.is_connected():
            state.voice_client = await member.voice.channel.connect()
        elif state.voice_client.channel != member.voice.channel:
            await state.voice_client.move_to(member.voice.channel)

        return state, state.voice_client

    def _play_next(self, guild_id: int) -> None:
        """Callback to play the next track when current one finishes."""
        state = self.bot.get_guild_state(guild_id)

        if state.voice_client is None or not state.voice_client.is_connected():
            state.is_playing = False
            return

        next_track = state.jukebox.next()
        if next_track is None:
            state.is_playing = False
            return

        self._play_track(state, next_track, guild_id)

    def _play_track(self, state: GuildState, track: Track, guild_id: int) -> None:
        """Play a track on the voice client."""
        if state.voice_client is None:
            return

        def after_playing(error: Exception | None) -> None:
            if error:
                logger.error(f"Playback error: {error}")
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

    @app_commands.command(name="play", description="Play a song from a URL")
    @app_commands.describe(url="The URL of the song to play (YouTube, SoundCloud, etc.)")
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
            await interaction.followup.send(f"Error fetching track: {e}")
            return

        position = state.jukebox.add(track)

        if not state.is_playing:
            next_track = state.jukebox.next()
            if next_track:
                self._play_track(state, next_track, guild_id)
                await interaction.followup.send(
                    f"Now playing: **{track.title}** [{track.format_duration()}]"
                )
        else:
            await interaction.followup.send(
                f"Added to queue at position {position + 1}: **{track.title}** [{track.format_duration()}]"
            )

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction) -> None:
        """Skip the current song."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.is_playing:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        current = state.jukebox.current
        state.voice_client.stop()  # This triggers the after callback
        await interaction.response.send_message(
            f"Skipped: **{current.title}**" if current else "Skipped."
        )

    @app_commands.command(name="queue", description="Show the current queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        """Display the current queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.jukebox.is_empty and state.jukebox.current is None:
            await interaction.response.send_message("The queue is empty.")
            return

        lines = []
        if state.jukebox.current:
            lines.append(
                f"**Now playing:** {state.jukebox.current.title} "
                f"[{state.jukebox.current.format_duration()}]"
            )

        queue = state.jukebox.queue
        if queue:
            lines.append("\n**Up next:**")
            for i, track in enumerate(queue[:10], 1):
                lines.append(f"{i}. {track.title} [{track.format_duration()}]")
            if len(queue) > 10:
                lines.append(f"... and {len(queue) - 10} more")

            total_duration = state.jukebox.get_queue_duration()
            hours, remainder = divmod(total_duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                lines.append(f"\n**Total queue time:** {hours}h {minutes}m")
            else:
                lines.append(f"\n**Total queue time:** {minutes}m {seconds}s")

        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="clear", description="Clear the queue")
    async def clear(self, interaction: discord.Interaction) -> None:
        """Clear all songs from the queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)
        count = state.jukebox.clear()
        await interaction.response.send_message(f"Cleared {count} tracks from the queue.")

    @app_commands.command(name="stop", description="Stop playback and disconnect")
    async def stop(self, interaction: discord.Interaction) -> None:
        """Stop playback, clear queue, and disconnect from voice."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None:
            await interaction.response.send_message("Not connected to a voice channel.")
            return

        state.jukebox.clear()
        state.jukebox.stop()
        state.is_playing = False
        await state.voice_client.disconnect()
        state.voice_client = None
        await interaction.response.send_message("Stopped playback and disconnected.")

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pause playback."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.voice_client.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        state.voice_client.pause()
        await interaction.response.send_message("Paused.")

    @app_commands.command(name="resume", description="Resume the paused song")
    async def resume(self, interaction: discord.Interaction) -> None:
        """Resume playback."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if state.voice_client is None or not state.voice_client.is_paused():
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)
            return

        state.voice_client.resume()
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name="nowplaying", description="Show the current song")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        """Show what's currently playing."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)
        current = state.jukebox.current

        if current is None:
            await interaction.response.send_message("Nothing is playing.")
            return

        await interaction.response.send_message(
            f"**Now playing:** {current.title} [{current.format_duration()}]\n"
            f"Requested by: {current.requester}"
        )

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        """Shuffle the queue."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        if len(state.jukebox.queue) < 2:
            await interaction.response.send_message(
                "Not enough tracks in queue to shuffle.", ephemeral=True
            )
            return

        state.jukebox.shuffle()
        await interaction.response.send_message("Queue shuffled!")

    @app_commands.command(name="remove", description="Remove a song from the queue")
    @app_commands.describe(position="The position of the song to remove (1-indexed)")
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        """Remove a song from the queue by position."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        state = self.bot.get_guild_state(interaction.guild.id)

        try:
            track = state.jukebox.remove(position - 1)
            await interaction.response.send_message(
                f"Removed: **{track.title}** from position {position}"
            )
        except IndexError:
            await interaction.response.send_message(
                f"Invalid position. Queue has {len(state.jukebox.queue)} tracks.",
                ephemeral=True,
            )
