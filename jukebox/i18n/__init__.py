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
