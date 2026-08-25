"""Conservative sitemap URL identity rules."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.monitor.urlnorm import normalize_url  # noqa: E402


def test_scheme_hostname_fragment_and_empty_path():
    assert normalize_url("HTTPS://EXAMPLE.COM#section") == "https://example.com/"


def test_default_ports_removed():
    assert normalize_url("http://Example.com:80/a") == "http://example.com/a"
    assert normalize_url("https://Example.com:443/a") == "https://example.com/a"
    assert normalize_url("https://Example.com:8443/a") == "https://example.com:8443/a"


def test_query_strings_are_preserved_not_sorted():
    assert normalize_url("https://EXAMPLE.com/a?b=2&a=1#x") == "https://example.com/a?b=2&a=1"
    assert normalize_url("https://example.com/a?a=1&b=2") != normalize_url(
        "https://example.com/a?b=2&a=1"
    )


def test_trailing_slashes_are_not_guessed_equivalent():
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/a/")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok: conservative URL normalization")
