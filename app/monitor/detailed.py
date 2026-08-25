"""Detailed page monitoring: extract one HTML response and diff content plus SEO fields."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, select

from ..config import settings
from ..models import Change, Page, Snapshot
from .diff import make_hunks


@dataclass(frozen=True)
class PageData:
    title: Optional[str]
    meta_description: Optional[str]
    h1: Optional[str]
    canonical: Optional[str]
    robots: Optional[str]
    visible_text: str


SEO_FIELDS = (
    "title",
    "meta_description",
    "h1",
    "canonical",
    "robots",
    "status_code",
    "final_url",
)

IMPORTANCE_WEIGHTS = {
    "robots": 100,
    "canonical": 95,
    "final_url": 90,
    "status_code": 90,
    "title": 75,
    "h1": 70,
    "meta_description": 45,
    "content": 30,
}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def _has_hidden_marker(node) -> bool:
    attrs = node.attributes or {}
    style = re.sub(r"\s+", "", (attrs.get("style") or "").lower())
    return (
        "hidden" in attrs
        or (attrs.get("aria-hidden") or "").lower() == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


def _is_hidden(node) -> bool:
    """Best-effort static visibility check for choosing the first meaningful H1."""
    current = node
    while current is not None:
        if _has_hidden_marker(current):
            return True
        current = current.parent
    return False


def _meta_content(tree, name: str) -> str | None:
    for node in tree.css("meta[name]"):
        if (node.attributes.get("name") or "").lower() == name:
            return _clean(node.attributes.get("content"))
    return None


def _canonical_href(tree) -> str | None:
    for node in tree.css("link[rel]"):
        rels = (node.attributes.get("rel") or "").lower().split()
        if "canonical" in rels:
            return _clean(node.attributes.get("href"))
    return None


def extract_page_data(html: bytes) -> PageData:
    """Extract bounded SEO metadata and normalized visible text from one HTML body."""
    from selectolax.parser import HTMLParser  # lazy import

    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = _clean(title_node.text(strip=True)) if title_node else None

    h1 = None
    for node in tree.css("h1"):
        if not _is_hidden(node):
            h1 = _clean(node.text(strip=True))
            if h1:
                break

    data = {
        "title": title,
        "meta_description": _meta_content(tree, "description"),
        "h1": h1,
        "canonical": _canonical_href(tree),
        "robots": _meta_content(tree, "robots"),
    }

    # Preserve the app's existing noise policy. These elements are omitted only from
    # visible content; metadata above was extracted before the nodes were removed.
    for selector in ("script", "style", "noscript", "nav", "footer", "svg", "header"):
        for node in tree.css(selector):
            node.decompose()
    for node in tree.css("*[hidden], *[aria-hidden], *[style]"):
        if _has_hidden_marker(node):
            node.decompose()

    root = tree.body or tree.root
    text = root.text(separator="\n") if root else ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    visible_text = "\n".join(line for line in lines if line)
    data["visible_text"] = visible_text[: max(0, settings.max_content_chars)]
    return PageData(**data)


def _snapshot_values(data: PageData, *, status_code: int, final_url: str) -> dict:
    return {
        "title": data.title,
        "meta_description": data.meta_description,
        "h1": data.h1,
        "canonical": data.canonical,
        "robots": data.robots,
        "status_code": status_code,
        "final_url": final_url,
    }


def _seo_changes(previous: Snapshot, current: dict) -> dict:
    return {
        field: {"from": getattr(previous, field), "to": current[field]}
        for field in SEO_FIELDS
        if getattr(previous, field) != current[field]
    }


def _importance_score(seo_changes: dict, content_changed: bool) -> int:
    score = sum(IMPORTANCE_WEIGHTS[field] for field in seo_changes)
    if content_changed:
        score += IMPORTANCE_WEIGHTS["content"]
    return min(100, score)


def _add_snapshot(
    session: Session,
    page: Page,
    data: PageData,
    content_hash: str,
    response_values: dict,
) -> None:
    session.add(
        Snapshot(
            page_id=page.id,
            content_hash=content_hash,
            content_text=data.visible_text,
            **response_values,
        )
    )


def _prune_snapshots(session: Session, page: Page) -> None:
    snapshots = session.exec(
        select(Snapshot)
        .where(Snapshot.page_id == page.id)
        .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
    ).all()
    retention = max(1, settings.snapshot_retention)
    for stale in snapshots[retention:]:
        session.delete(stale)


def check_page_content(session: Session, page: Page, client) -> Change | None:
    """Fetch and compare one page, returning a ``modified`` change when anything differs."""
    from . import fetch  # lazy import

    conditional: dict[str, str] = {}
    if page.etag:
        conditional["If-None-Match"] = page.etag
    if page.last_modified:
        conditional["If-Modified-Since"] = page.last_modified

    try:
        response = fetch.polite_get(client, page.url, conditional=conditional or None)
        if response.status_code == 304:
            _prune_snapshots(session, page)
            return None
    except fetch.Blocked as exc:
        if exc.response is None:
            return None
        # Preserve the status from the request that triggered a 403/429 cooldown. Future
        # attempts during the cooldown have no response and return through the branch above.
        response = exc.response
    except Exception:
        return None  # one blocked or failed page must not abort the competitor crawl

    page.etag = response.headers.get("ETag")
    page.last_modified = response.headers.get("Last-Modified")

    data = extract_page_data(response.content)
    content_hash = hashlib.sha256(data.visible_text.encode("utf-8")).hexdigest()
    response_values = _snapshot_values(
        data,
        status_code=response.status_code,
        final_url=str(response.url),
    )
    previous = session.exec(
        select(Snapshot)
        .where(Snapshot.page_id == page.id)
        .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
    ).first()

    page.latest_content_hash = content_hash
    session.add(page)

    if previous is None:
        _add_snapshot(session, page, data, content_hash, response_values)
        session.flush()
        _prune_snapshots(session, page)
        return None

    seo_changes = _seo_changes(previous, response_values)
    content_changed = previous.content_hash != content_hash
    if not seo_changes and not content_changed:
        _prune_snapshots(session, page)
        return None

    detail = {
        "title": data.title,
        "seo_changes": seo_changes,
        "content_changed": content_changed,
        "hunks": make_hunks(previous.content_text, data.visible_text) if content_changed else [],
        "importance_score": _importance_score(seo_changes, content_changed),
    }
    change = Change(
        competitor_id=page.competitor_id,
        page_id=page.id,
        type="modified",
        detail=detail,
    )
    session.add(change)
    _add_snapshot(session, page, data, content_hash, response_values)
    session.flush()  # give the new row an id before retention ordering/pruning
    _prune_snapshots(session, page)
    return change
