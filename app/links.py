from urllib.parse import urlsplit, urlunsplit
import re

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def normalize_username(value: str) -> str:
    value = (value or "").strip()
    value = value.removeprefix("@")
    if not USERNAME_RE.fullmatch(value):
        raise ValueError("Enter a valid Telegram bot username (5–32 letters, digits, underscores; starts with a letter).")
    return value


def replace_bot_username(url: str, old_username: str, new_username: str) -> str | None:
    """Return updated URL only for matching Telegram bot deep links; otherwise None.

    The query and fragment are retained verbatim by urlunsplit. Only the path username
    is changed. urlsplit preserves query text, including the exact start token.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    old_username = normalize_username(old_username)
    new_username = normalize_username(new_username)
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("https", "http", ""):
        return None
    host = (parts.hostname or "").lower()
    if host not in ("t.me", "www.t.me", "telegram.me", "www.telegram.me"):
        return None
    path = parts.path
    if path.startswith("/"):
        path = path[1:]
    # A bot deep link must have the username as the first path segment.
    segments = path.split("/")
    if not segments or segments[0].casefold() != old_username.casefold():
        return None
    segments[0] = new_username
    new_path = "/" + "/".join(segments)
    # Keep the original scheme/netloc/query/fragment. If scheme was omitted,
    # normalize to https so the resulting button is a valid URL.
    scheme = parts.scheme or "https"
    netloc = parts.netloc or "t.me"
    return urlunsplit((scheme, netloc, new_path, parts.query, parts.fragment))


def is_matching_url(url: str, old_username: str) -> bool:
    return replace_bot_username(url, old_username, "RecoveryBot") is not None
