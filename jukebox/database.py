"""Database module for Jukebox with SQLite storage."""

import sqlite3
from pathlib import Path
from typing import Literal

# Database file location (in the jukebox package directory)
DATABASE_PATH = Path(__file__).parent / "jukebox.db"

# Association types for the polymorphic table
AssociationType = Literal["user", "guild"]

# Default language when no association exists
DEFAULT_LANGUAGE = "en"


def get_connection() -> sqlite3.Connection:
    """Get a database connection.

    Returns:
        A SQLite connection to the database.
    """
    return sqlite3.connect(DATABASE_PATH)


def run_migrations() -> None:
    """Run all database migrations.

    Creates tables if they don't exist and applies any pending migrations.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Create migrations tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Get applied migrations
    cursor.execute("SELECT name FROM migrations")
    applied = {row[0] for row in cursor.fetchall()}

    # Define migrations in order
    migrations = [
        ("001_create_language_associations", _migration_001_create_language_associations),
    ]

    # Apply pending migrations
    for name, migration_fn in migrations:
        if name not in applied:
            migration_fn(cursor)
            cursor.execute("INSERT INTO migrations (name) VALUES (?)", (name,))

    conn.commit()
    conn.close()


def _migration_001_create_language_associations(cursor: sqlite3.Cursor) -> None:
    """Create the language_associations table.

    This is a polymorphic table that stores language preferences for both
    users and guilds. The 'type' column indicates whether the entity_id
    refers to a user or guild.

    Columns:
        - type: 'user' or 'guild'
        - entity_id: The Discord user ID or guild ID
        - language: The language code (e.g., 'en', 'es', 'de')
    """
    cursor.execute("""
        CREATE TABLE language_associations (
            type TEXT NOT NULL CHECK (type IN ('user', 'guild')),
            entity_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            PRIMARY KEY (type, entity_id)
        )
    """)
    # Index for faster lookups by entity
    cursor.execute("""
        CREATE INDEX idx_language_associations_lookup
        ON language_associations (type, entity_id)
    """)


def set_language(association_type: AssociationType, entity_id: int, language: str) -> None:
    """Set the language for a user or guild.

    Args:
        association_type: Either 'user' or 'guild'.
        entity_id: The Discord user ID or guild ID.
        language: The language code to set.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO language_associations (type, entity_id, language)
        VALUES (?, ?, ?)
    """, (association_type, entity_id, language))

    conn.commit()
    conn.close()


def get_language(association_type: AssociationType, entity_id: int) -> str | None:
    """Get the language for a user or guild.

    Args:
        association_type: Either 'user' or 'guild'.
        entity_id: The Discord user ID or guild ID.

    Returns:
        The language code if set, None otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT language FROM language_associations
        WHERE type = ? AND entity_id = ?
    """, (association_type, entity_id))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def get_effective_language(user_id: int | None, guild_id: int | None) -> str:
    """Get the effective language for a context.

    Checks for a user language first, then guild language, then defaults to English.

    Args:
        user_id: The Discord user ID, or None.
        guild_id: The Discord guild ID, or None.

    Returns:
        The effective language code for this context.
    """
    # First priority: user's personal language preference
    if user_id is not None:
        user_language = get_language("user", user_id)
        if user_language is not None:
            return user_language

    # Second priority: guild's language preference
    if guild_id is not None:
        guild_language = get_language("guild", guild_id)
        if guild_language is not None:
            return guild_language

    # Default to English
    return DEFAULT_LANGUAGE


def remove_language(association_type: AssociationType, entity_id: int) -> bool:
    """Remove the language setting for a user or guild.

    Args:
        association_type: Either 'user' or 'guild'.
        entity_id: The Discord user ID or guild ID.

    Returns:
        True if a record was deleted, False if no record existed.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM language_associations
        WHERE type = ? AND entity_id = ?
    """, (association_type, entity_id))

    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return deleted
