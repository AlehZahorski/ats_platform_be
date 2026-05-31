"""Logging building blocks — audit_logging_monitoring follow-up.

Three pieces:

1. ``request_id_ctx`` — a ``contextvars.ContextVar`` that holds the current
   request id. Set by the middleware in ``main.py``, read by the formatter
   below.
2. ``RequestIdFilter`` — a stdlib ``logging.Filter`` that injects the current
   request id into every ``LogRecord``. Plugged into the root logger.
3. ``PiiRedactionFilter`` — a defence-in-depth ``logging.Filter`` that
   redacts the obvious PII shapes (emails, Polish phone numbers) before the
   record reaches any handler. Code should still avoid logging PII; this
   only catches accidents.

Keeping these as plain stdlib pieces means we can ship a real observability
stack (structlog / OTel / Sentry) later without breaking call sites.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

# F-03 (audit_logging_monitoring): single source of truth for the current
# request id. ``set`` returns a token; the middleware that calls it resets
# the contextvar on the way out so nothing leaks between requests.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    """Short hex id — 12 chars is enough to grep and short enough not to
    bloat every log line."""
    return uuid.uuid4().hex[:12]


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every record as ``record.request_id``.

    The default stdlib formatter does not understand contextvars, so we
    materialise the id onto the record object itself. Format strings can then
    reference ``%(request_id)s``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


# F-17: pre-compiled redaction patterns. Order matters — phones first because
# they can contain `@` in international formats embedded in markdown.
_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]?\d{3}[\s-]?\d{2,4}[\s-]?\d{2,4}(?!\d)"
)


def _redact(value: str) -> str:
    value = _EMAIL_RE.sub("<email-redacted>", value)
    value = _PHONE_RE.sub("<phone-redacted>", value)
    return value


class PiiRedactionFilter(logging.Filter):
    """Best-effort PII redaction at the logging layer.

    audit_logging_monitoring F-17: code is supposed to keep PII out of logs
    in the first place, but accidents (an exception message containing a
    candidate's email, a debug log of a request body) do happen. This filter
    rewrites the rendered message before it leaves the process. It is fast —
    two compiled regexes — and stays a no-op when there is nothing to redact.

    Only the rendered ``msg`` and known PII-shaped ``extra`` fields are
    touched; structured numeric / id fields pass through untouched so they
    can be correlated later.
    """

    _STRING_EXTRA_FIELDS = ("email", "phone", "candidate_email", "user_email")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            try:
                record.args = tuple(_redact(a) if isinstance(a, str) else a for a in record.args)
            except Exception:  # noqa: BLE001 — never let logging crash callers
                pass
        for field in self._STRING_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, str):
                setattr(record, field, _redact(value))
        return True


_ORIGINAL_RECORD_FACTORY = logging.getLogRecordFactory()


def _request_id_record_factory(*args, **kwargs):
    """LogRecordFactory wrapper that stamps every record with the current
    request id at creation time.

    Stdlib filters on the root logger only fire for records *originating*
    from that logger — child loggers (uvicorn, sqlalchemy, our own modules)
    bypass them. A LogRecordFactory runs for every record regardless of
    where it was created, which is what we actually want here.
    """
    record = _ORIGINAL_RECORD_FACTORY(*args, **kwargs)
    record.request_id = request_id_ctx.get()
    return record


_INSTALLED = False


def install_root_filters() -> None:
    """Idempotent — installs the request-id LogRecordFactory and attaches the
    PII filter to the root logger.

    PII redaction can live on the root logger because filters DO run for
    records passing through ancestor *handlers*, and that's what
    redaction needs. The request-id stamping moves to the record factory
    so every record carries the field whether or not a handler asks for it.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    logging.setLogRecordFactory(_request_id_record_factory)
    root = logging.getLogger()
    if not any(isinstance(f, PiiRedactionFilter) for f in root.filters):
        root.addFilter(PiiRedactionFilter())
    _INSTALLED = True
