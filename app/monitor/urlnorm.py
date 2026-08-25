"""Conservative URL normalization for sitemap inventory comparisons."""
from __future__ import annotations

from urllib.parse import SplitResult, urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """Normalize only URL parts whose equivalence is safe to assume.

    Query strings and non-empty paths are deliberately preserved byte-for-byte.
    The original discovered URL remains stored on ``Page`` for display and fetching.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    hostname = parts.hostname

    # Relative URLs are not valid sitemap entries, but preserving them is safer than
    # inventing an authority if one reaches this helper.
    if hostname is None:
        return urlunsplit((scheme, parts.netloc, parts.path or "/", parts.query, ""))

    host = hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"  # urlsplit strips brackets from IPv6 hostnames

    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"

    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        userinfo += "@"

    normalized = SplitResult(scheme, f"{userinfo}{host}", parts.path or "/", parts.query, "")
    return normalized.geturl()
