"""Basic (sitemap-only) change detection.

Pure-python, dependency-free, so it can be unit-tested directly. Given the previously
stored pages and a freshly-fetched sitemap, it produces added / sitemap_removed /
suspected records.

'suspected' = a page present in both runs whose <lastmod> changed. It only means "this page
probably changed" — sitemaps never reveal *what* changed. Seeing the actual content diff is
the job of detailed monitoring (see detailed.py, milestone M4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .sitemap import PageEntry
from .urlnorm import normalize_url


@dataclass
class ChangeRec:
    type: str  # "added" | "sitemap_removed" | "suspected"
    url: str
    detail: dict = field(default_factory=dict)


def diff_pages(old: dict[str, str | None], new_entries: list[PageEntry]) -> list[ChangeRec]:
    """Compare active pages with fresh entries using conservative normalized URLs."""
    old_map = {normalize_url(url): (url, lastmod) for url, lastmod in old.items()}
    # Keep the first spelling found in the sitemap. It is the original URL we will store
    # and fetch, while the dictionary key is used only for identity comparisons.
    new_map: dict[str, PageEntry] = {}
    for entry in new_entries:
        new_map.setdefault(normalize_url(entry.loc), entry)

    old_urls, new_urls = set(old_map), set(new_map)
    changes: list[ChangeRec] = []

    for normalized in new_urls - old_urls:
        changes.append(ChangeRec("added", new_map[normalized].loc))

    for normalized in old_urls - new_urls:
        changes.append(ChangeRec("sitemap_removed", old_map[normalized][0]))

    for normalized in old_urls & new_urls:
        new_entry = new_map[normalized]
        old_url, old_lastmod = old_map[normalized]
        # Only a *changed, present* lastmod counts as a suspected modification.
        if new_entry.lastmod and new_entry.lastmod != old_lastmod:
            changes.append(
                ChangeRec(
                    "suspected",
                    old_url,
                    {"lastmod_from": old_lastmod, "lastmod_to": new_entry.lastmod},
                )
            )

    return changes
