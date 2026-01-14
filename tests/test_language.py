"""Unit tests for language/database functionality."""

import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)

    # Patch the DATABASE_PATH in the database module
    with mock.patch("jukebox.database.DATABASE_PATH", temp_path):
        # Import after patching to use the temp path
        from jukebox.database import run_migrations

        run_migrations()
        yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


class TestDatabaseMigrations:
    """Tests for database migrations."""

    def test_migrations_create_tables(self, temp_db: Path) -> None:
        """Test that migrations create the required tables."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Check that migrations table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migrations'"
        )
        assert cursor.fetchone() is not None

        # Check that language_associations table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='language_associations'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_migrations_are_idempotent(self, temp_db: Path) -> None:
        """Test that running migrations multiple times is safe."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import run_migrations

            # Run migrations again - should not raise
            run_migrations()
            run_migrations()

    def test_language_associations_schema(self, temp_db: Path) -> None:
        """Test that language_associations table has correct schema."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(language_associations)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "type" in columns
        assert "entity_id" in columns
        assert "language" in columns

        conn.close()


class TestSetLanguage:
    """Tests for setting language preferences."""

    def test_set_user_language(self, temp_db: Path) -> None:
        """Test setting a user's language preference."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language, set_language

            set_language("user", 12345, "es")
            result = get_language("user", 12345)

            assert result == "es"

    def test_set_guild_language(self, temp_db: Path) -> None:
        """Test setting a guild's language preference."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language, set_language

            set_language("guild", 67890, "de")
            result = get_language("guild", 67890)

            assert result == "de"

    def test_update_existing_language(self, temp_db: Path) -> None:
        """Test updating an existing language preference."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language, set_language

            set_language("user", 12345, "es")
            set_language("user", 12345, "fr")
            result = get_language("user", 12345)

            assert result == "fr"

    def test_multiple_associations(self, temp_db: Path) -> None:
        """Test storing multiple language associations."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language, set_language

            set_language("user", 111, "es")
            set_language("user", 222, "de")
            set_language("guild", 333, "fr")
            set_language("guild", 444, "ja")

            assert get_language("user", 111) == "es"
            assert get_language("user", 222) == "de"
            assert get_language("guild", 333) == "fr"
            assert get_language("guild", 444) == "ja"


class TestGetLanguage:
    """Tests for retrieving language preferences."""

    def test_get_nonexistent_user_language(self, temp_db: Path) -> None:
        """Test getting language for a user that hasn't set one."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language

            result = get_language("user", 99999)

            assert result is None

    def test_get_nonexistent_guild_language(self, temp_db: Path) -> None:
        """Test getting language for a guild that hasn't set one."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language

            result = get_language("guild", 99999)

            assert result is None


class TestGetEffectiveLanguage:
    """Tests for the effective language lookup logic."""

    def test_user_language_takes_priority(self, temp_db: Path) -> None:
        """Test that user language takes priority over guild language."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_effective_language, set_language

            set_language("user", 12345, "es")
            set_language("guild", 67890, "de")

            result = get_effective_language(user_id=12345, guild_id=67890)

            assert result == "es"

    def test_guild_language_as_fallback(self, temp_db: Path) -> None:
        """Test that guild language is used when user has no preference."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_effective_language, set_language

            set_language("guild", 67890, "de")

            result = get_effective_language(user_id=12345, guild_id=67890)

            assert result == "de"

    def test_default_to_english(self, temp_db: Path) -> None:
        """Test that English is used when no preferences are set."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_effective_language

            result = get_effective_language(user_id=12345, guild_id=67890)

            assert result == "en"

    def test_user_only_context(self, temp_db: Path) -> None:
        """Test effective language with only user_id (DM context)."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_effective_language, set_language

            set_language("user", 12345, "ja")

            result = get_effective_language(user_id=12345, guild_id=None)

            assert result == "ja"

    def test_guild_only_context(self, temp_db: Path) -> None:
        """Test effective language with only guild_id."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_effective_language, set_language

            set_language("guild", 67890, "ko")

            result = get_effective_language(user_id=None, guild_id=67890)

            assert result == "ko"

    def test_no_context_defaults_to_english(self, temp_db: Path) -> None:
        """Test effective language with no user_id or guild_id."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_effective_language

            result = get_effective_language(user_id=None, guild_id=None)

            assert result == "en"


class TestRemoveLanguage:
    """Tests for removing language preferences."""

    def test_remove_user_language(self, temp_db: Path) -> None:
        """Test removing a user's language preference."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language, remove_language, set_language

            set_language("user", 12345, "es")
            result = remove_language("user", 12345)

            assert result is True
            assert get_language("user", 12345) is None

    def test_remove_guild_language(self, temp_db: Path) -> None:
        """Test removing a guild's language preference."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import get_language, remove_language, set_language

            set_language("guild", 67890, "de")
            result = remove_language("guild", 67890)

            assert result is True
            assert get_language("guild", 67890) is None

    def test_remove_nonexistent_language(self, temp_db: Path) -> None:
        """Test removing a language preference that doesn't exist."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import remove_language

            result = remove_language("user", 99999)

            assert result is False


class TestI18nLocale:
    """Tests for i18n locale functions."""

    def test_get_available_locales(self) -> None:
        """Test getting available locale codes."""
        from jukebox.i18n import get_available_locales

        locales = get_available_locales()

        assert isinstance(locales, list)
        assert "en" in locales
        assert len(locales) > 0

    def test_is_valid_locale_true(self) -> None:
        """Test is_valid_locale returns True for valid locales."""
        from jukebox.i18n import is_valid_locale

        assert is_valid_locale("en") is True

    def test_is_valid_locale_false(self) -> None:
        """Test is_valid_locale returns False for invalid locales."""
        from jukebox.i18n import is_valid_locale

        assert is_valid_locale("invalid_locale_xyz") is False


class TestI18nContextualTranslation:
    """Tests for context-aware translations."""

    def test_t_for_returns_spanish_when_user_language_is_spanish(self, temp_db: Path) -> None:
        """Test t_for returns Spanish translation when user language is Spanish."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import set_language
            from jukebox.i18n import I18n, t_for

            set_language("user", 12345, "es")

            result = t_for(user_id=12345, guild_id=None, key="response.paused")
            spanish_expected = I18n("es").get("response.paused")
            english_text = I18n("en").get("response.paused")

            # Verify it returns Spanish, not English
            assert result == spanish_expected
            assert result == "Pausado."
            assert result != english_text

    def test_t_for_returns_spanish_when_guild_language_is_spanish(self, temp_db: Path) -> None:
        """Test t_for returns Spanish translation when guild language is Spanish."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import set_language
            from jukebox.i18n import I18n, t_for

            set_language("guild", 67890, "es")

            # User 12345 has no language set, should fall back to guild
            result = t_for(user_id=12345, guild_id=67890, key="response.paused")
            spanish_expected = I18n("es").get("response.paused")
            english_text = I18n("en").get("response.paused")

            assert result == spanish_expected
            assert result == "Pausado."
            assert result != english_text

    def test_user_language_overrides_guild_language(self, temp_db: Path) -> None:
        """Test that user language takes priority over guild language."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import set_language
            from jukebox.i18n import I18n, t_for

            # Guild is German, but user is Spanish
            set_language("guild", 67890, "de")
            set_language("user", 12345, "es")

            result = t_for(user_id=12345, guild_id=67890, key="response.paused")
            spanish_text = I18n("es").get("response.paused")
            german_text = I18n("de").get("response.paused")

            # Should use Spanish (user), not German (guild)
            assert result == spanish_text
            assert result != german_text

    def test_t_for_defaults_to_english_when_no_language_set(self, temp_db: Path) -> None:
        """Test t_for defaults to English when no language is set."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.i18n import I18n, t_for

            result = t_for(user_id=12345, guild_id=67890, key="response.paused")
            english_expected = I18n("en").get("response.paused")

            assert result == english_expected
            assert result == "Paused."

    def test_t_for_with_format_args_in_spanish(self, temp_db: Path) -> None:
        """Test t_for properly formats string arguments in non-English languages."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import set_language
            from jukebox.i18n import t_for

            set_language("user", 12345, "es")

            result = t_for(
                user_id=12345,
                guild_id=None,
                key="response.now_playing",
                title="Test Song",
                duration="3:45",
            )

            # Should contain the Spanish text with interpolated values
            assert "Test Song" in result
            assert "3:45" in result
            assert "Reproduciendo ahora" in result  # Spanish for "Now playing"
            assert "Now playing" not in result  # Should NOT contain English

    def test_t_for_queue_empty_in_spanish(self, temp_db: Path) -> None:
        """Test a simple translation key returns Spanish when language is set."""
        with mock.patch("jukebox.database.DATABASE_PATH", temp_db):
            from jukebox.database import set_language
            from jukebox.i18n import t_for

            set_language("user", 12345, "es")

            result = t_for(user_id=12345, guild_id=None, key="response.queue_empty")

            assert result == "La cola está vacía."
            assert result != "The queue is empty."
