from urllib.parse import urlparse

#: Only absolute web URLs are safe to store and render as links/images. Everything
#: else (javascript:, data:, file:, protocol-relative URLs, ...) can be used for
#: URL injection in whatever page eventually renders the value.
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def is_http_url(value: str) -> bool:
    """Return whether a (stripped) non-empty string is an absolute HTTP(S) URL."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    hostname = parsed.hostname
    return parsed.scheme.lower() in ALLOWED_URL_SCHEMES and hostname is not None and hostname != ""


def sanitize_http_url(value: object) -> str:
    """
    Return ``value`` when it is an HTTP(S) URL, otherwise an empty string.

    Non-string input (e.g. ``None`` from a JSON payload) is treated as absent.
    """
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if is_http_url(value) else ""


def invalid_http_urls(values: dict[str, str]) -> list[str]:
    """Return the names of non-empty values that are not absolute HTTP(S) URLs."""
    return [name for name, value in values.items() if value != "" and not is_http_url(value)]
