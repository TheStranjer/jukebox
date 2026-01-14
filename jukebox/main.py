"""Main entry point for the Jukebox Discord bot."""

import logging
import os
import sys

from dotenv import load_dotenv

from .bot import JukeboxBot


def main() -> None:
    """Run the Jukebox bot."""
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set.", file=sys.stderr)
        print("Please set it in a .env file or as an environment variable.", file=sys.stderr)
        sys.exit(1)

    bot = JukeboxBot()
    bot.run(token)


if __name__ == "__main__":
    main()
