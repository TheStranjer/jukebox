# Jukebox

A Discord bot that plays audio from YouTube and other sources using slash commands.

## Features

- Play audio from YouTube, SoundCloud, and many other sources (via yt-dlp)
- Queue management with add, remove, shuffle, and clear
- Playback controls: play, pause, resume, skip, stop
- Shows currently playing track and queue status
- Per-server queues (each Discord server has its own queue)

## Requirements

- Python 3.10+
- FFmpeg installed on your system
- A Discord bot token

## Installation

### One-step install (recommended)

Run the installer from the repo root:
```bash
./scripts/install.sh
```

Options:
```bash
./scripts/install.sh --systemd
./scripts/install.sh --no-systemd
./scripts/install.sh --discord-token=YOUR_TOKEN
./scripts/install.sh --service-user=jukebox
```

The installer will:
- Create a virtual environment and install dependencies
- Prompt for your Discord bot token (unless provided)
- Optionally set up and start a systemd service when run as root
- Ask whether to create a dedicated service user (default name: jukebox)

If you pass `--service-user=NAME`, the installer skips user prompts and uses that
service user. If the user already exists, it is reused; otherwise it is created.
To skip user creation entirely, set `--service-user` to your current user.
This flag only applies when systemd is enabled.

### Manual install

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd jukebox
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Install FFmpeg:
   - **Ubuntu/Debian:** `sudo apt install ffmpeg`
   - **macOS:** `brew install ffmpeg`
   - **Windows:** Download from https://ffmpeg.org/download.html

4. Create a `.env` file with your Discord bot token:
   ```
   DISCORD_TOKEN=your_bot_token_here
   ```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section and create a bot
4. Copy the bot token and add it to your `.env` file
5. Go to "OAuth2" > "URL Generator"
6. Select scopes: `bot`, `applications.commands`
7. Select bot permissions: `Connect`, `Speak`, `Send Messages`
8. Use the generated URL to invite the bot to your server

## Usage

Start the bot:
```bash
python -m jukebox.main
```

### Slash Commands

| Command | Description |
|---------|-------------|
| `/play <url>` | Add a song to the queue and start playing |
| `/skip` | Skip the current song |
| `/queue` | Show the current queue |
| `/nowplaying` | Show the currently playing song |
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/stop` | Stop playback and disconnect from voice |
| `/clear` | Clear all songs from the queue |
| `/shuffle` | Shuffle the queue |
| `/remove <position>` | Remove a song from the queue by position |

## Running Tests

```bash
pytest
```

## Architecture

The project separates business logic from I/O for testability:

- **`jukebox/jukebox.py`** - Core queue management logic (fully unit tested)
- **`jukebox/track.py`** - Track data class
- **`jukebox/audio_source.py`** - Audio fetching protocol and yt-dlp implementation
- **`jukebox/bot.py`** - Discord bot with slash commands (I/O layer)
- **`jukebox/main.py`** - Entry point

## License

MIT
