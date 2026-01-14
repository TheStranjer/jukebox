"""Internationalization module for Jukebox."""

from pathlib import Path

import yaml


class I18n:
    """Simple i18n class for loading and accessing translations."""

    def __init__(self, locale: str = "en"):
        """Initialize i18n with the specified locale.

        Args:
            locale: The locale to load (default: "en").
        """
        self._translations: dict = {}
        self._locale = locale
        self._load_translations()

    def _load_translations(self) -> None:
        """Load translations from the YAML file."""
        i18n_dir = Path(__file__).parent
        yaml_path = i18n_dir / f"{self._locale}.yaml"

        if yaml_path.exists():
            with open(yaml_path, encoding="utf-8") as f:
                self._translations = yaml.safe_load(f) or {}

    def get(self, key: str, **kwargs: object) -> str:
        """Get a translated string by dot-notation key.

        Args:
            key: The dot-notation key (e.g., "error.need_voice_channel").
            **kwargs: Values to substitute into the string.

        Returns:
            The translated string with substitutions applied.
        """
        parts = key.split(".")
        value: dict | str = self._translations

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return key  # Return key if not found

        if isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError:
                return value
        return key


# Global instance with default locale
_i18n = I18n()


def t(key: str, **kwargs: object) -> str:
    """Get a translated string.

    Args:
        key: The dot-notation key (e.g., "error.need_voice_channel").
        **kwargs: Values to substitute into the string.

    Returns:
        The translated string with substitutions applied.
    """
    return _i18n.get(key, **kwargs)


def set_locale(locale: str) -> None:
    """Set the current locale.

    Args:
        locale: The locale to use.
    """
    global _i18n
    _i18n = I18n(locale)


def get_available_locales() -> list[str]:
    """Get a list of all available locale codes.

    Returns:
        A list of locale codes (e.g., ['en', 'es', 'de', ...]).
    """
    i18n_dir = Path(__file__).parent
    locales = []
    for yaml_file in i18n_dir.glob("*.yaml"):
        locales.append(yaml_file.stem)
    return sorted(locales)


def is_valid_locale(locale: str) -> bool:
    """Check if a locale code is valid (has a translation file).

    Args:
        locale: The locale code to check.

    Returns:
        True if the locale is valid, False otherwise.
    """
    return locale in get_available_locales()


def t_for(user_id: int | None, guild_id: int | None, key: str, **kwargs: object) -> str:
    """Get a translated string for a specific user/guild context.

    This function checks for user language first, then guild language,
    then defaults to English.

    Args:
        user_id: The Discord user ID, or None.
        guild_id: The Discord guild ID, or None.
        key: The dot-notation key (e.g., "error.need_voice_channel").
        **kwargs: Values to substitute into the string.

    Returns:
        The translated string with substitutions applied.
    """
    # Import here to avoid circular imports
    from ..database import get_effective_language

    locale = get_effective_language(user_id, guild_id)
    i18n = I18n(locale)
    return i18n.get(key, **kwargs)
