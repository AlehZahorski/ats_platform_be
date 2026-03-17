"""
Language detection utility for v2 i18n support.

Usage in endpoints:
    from app.core.i18n import detect_language

    @router.post("/apply/{job_id}")
    async def apply(request: Request, ...):
        language = detect_language(request)
"""

from fastapi import Request

SUPPORTED_LANGUAGES = {"en", "pl"}
DEFAULT_LANGUAGE = "en"


def detect_language(request: Request) -> str:
    """
    Detect the preferred language for a request.

    Priority:
    1. `lang` query param  (?lang=pl)
    2. `locale` cookie (set by frontend language switcher)
    3. `Accept-Language` header
    4. Default: 'en'
    """
    # 1. Query param
    lang = request.query_params.get("lang")
    if lang and lang in SUPPORTED_LANGUAGES:
        return lang

    # 2. Cookie
    locale_cookie = request.cookies.get("locale")
    if locale_cookie and locale_cookie in SUPPORTED_LANGUAGES:
        return locale_cookie

    # 3. Accept-Language header
    accept_language = request.headers.get("Accept-Language", "")
    for part in accept_language.split(","):
        code = part.strip().split(";")[0].strip()[:2].lower()
        if code in SUPPORTED_LANGUAGES:
            return code

    return DEFAULT_LANGUAGE


def get_user_language(user) -> str:
    """Get language from user model, fallback to default."""
    lang = getattr(user, "language", DEFAULT_LANGUAGE)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
