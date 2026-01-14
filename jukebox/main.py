"""Main entry point for the Jukebox Discord bot."""

import logging
import os
import sys

from dotenv import load_dotenv

from .bot import JukeboxBot
from .database import run_migrations
from .i18n import t


def main() -> None:
    """Run the Jukebox bot."""
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run database migrations
    run_migrations()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print(t("error.discord_token_not_set"), file=sys.stderr)
        print(t("error.discord_token_instructions"), file=sys.stderr)
        sys.exit(1)

    bot = JukeboxBot()
    bot.run(token)


if __name__ == "__main__":
    main()
