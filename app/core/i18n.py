"""
Internationalisation (i18n) utilities.

Usage in services / routers:
    from app.core.i18n import t
    raise NotFoundError(t("applications.not_found"))

Language is set automatically per-request by the language middleware in main.py.
It can also be overridden via ?lang=pl query param, locale cookie, or Accept-Language header.
"""

import json
import re
from contextvars import ContextVar
from pathlib import Path

from fastapi import Request

SUPPORTED_LANGUAGES = {"en", "pl"}
DEFAULT_LANGUAGE = "en"

# ---------------------------------------------------------------------------
# Per-request language context
# ---------------------------------------------------------------------------
_lang_var: ContextVar[str] = ContextVar("language", default=DEFAULT_LANGUAGE)


def get_language() -> str:
    return _lang_var.get()


def set_language(lang: str) -> None:
    _lang_var.set(lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE)


# ---------------------------------------------------------------------------
# Translation lookup
# ---------------------------------------------------------------------------
_translations: dict[str, dict[str, str]] = {}


def _load_translations() -> None:
    base = Path(__file__).parent.parent / "i18n"
    for lang in SUPPORTED_LANGUAGES:
        path = base / f"{lang}.json"
        if path.exists():
            _translations[lang] = json.loads(path.read_text(encoding="utf-8"))


_load_translations()


def t(key: str, **kwargs: object) -> str:
    """Return the translated string for *key* in the current request language.

    Falls back to English if the key is missing in the active language.
    Falls back to the key itself if missing in all languages.
    Interpolates named placeholders with **kwargs.
    """
    lang = _lang_var.get()
    msg = (
        _translations.get(lang, {}).get(key)
        or _translations.get(DEFAULT_LANGUAGE, {}).get(key)
        or key
    )
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, ValueError):
            return msg
    return msg


# ---------------------------------------------------------------------------
# Language detection from request
# ---------------------------------------------------------------------------
def detect_language(request: Request) -> str:
    """Detect the preferred language for a request.

    Priority:
    1. `lang` query param  (?lang=pl)
    2. `locale` cookie (set by frontend language switcher)
    3. `Accept-Language` header
    4. Default: 'en'
    """
    lang = request.query_params.get("lang")
    if lang and lang in SUPPORTED_LANGUAGES:
        return lang

    locale_cookie = request.cookies.get("locale")
    if locale_cookie and locale_cookie in SUPPORTED_LANGUAGES:
        return locale_cookie

    accept_language = request.headers.get("Accept-Language", "")
    for part in accept_language.split(","):
        code = part.strip().split(";")[0].strip()[:2].lower()
        if code in SUPPORTED_LANGUAGES:
            return code

    return DEFAULT_LANGUAGE


def get_user_language(user: object) -> str:
    """Get language from user model, fallback to default."""
    lang = getattr(user, "language", DEFAULT_LANGUAGE)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Content language detection (heuristic — PL vs EN)
# ---------------------------------------------------------------------------
_PL_DIACRITICS = frozenset("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")

# Common Polish function words / stopwords that rarely appear in English.
# Includes ASCII-folded variants (e.g. ``sie``) because Polish recruiters
# sometimes type without diacritics.
_PL_STOPWORDS = frozenset({
    # Diacritic forms
    "się", "który", "która", "które", "którego", "której", "których",
    "być", "także", "również", "zespołu",
    # Diacritic-free forms (same words)
    "sie", "ktory", "ktora", "ktore", "ktorego", "ktorej", "ktorych",
    "byc", "takze", "rowniez", "zespolu",
    # Words without diacritics
    "oraz", "jest", "lub", "albo", "tylko", "wszystkie", "dla", "przez",
    "podczas", "powinien", "powinna", "naszej", "naszego", "rozwoju",
    "pracy", "stanowisku", "firmie", "wymagania", "kandydat", "osoby",
})

_WORD_RE = re.compile(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+")


def detect_text_language(text: str | None, fallback: str = DEFAULT_LANGUAGE) -> str:
    """Detect whether ``text`` looks Polish, otherwise return ``fallback``.

    Heuristic — fast and dependency-free. Polish-only diacritics
    (ą/ć/ę/ł/ń/ó/ś/ź/ż) never appear in English, so just a few of them
    is a strong signal. Two independent rules each trigger ``"pl"``:

      • ≥ 2 Polish-specific diacritics, OR
      • ≥ 2 Polish stopwords (case-insensitive)

    Returns ``fallback`` (default ``"en"``) when neither signal fires or
    when the text is empty.
    """
    if not text:
        return fallback

    diacritic_count = sum(1 for c in text if c in _PL_DIACRITICS)
    if diacritic_count >= 2:
        return "pl"

    words = (m.group(0).lower() for m in _WORD_RE.finditer(text))
    pl_word_count = 0
    for w in words:
        if w in _PL_STOPWORDS:
            pl_word_count += 1
            if pl_word_count >= 2:
                return "pl"

    return fallback
