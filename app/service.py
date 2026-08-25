"""Check orchestration — what runs on a schedule or when triggered manually."""
from __future__ import annotations

from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import Change, Competitor, Page
from .monitor.basic import diff_pages
from .monitor.detailed import check_page_content
from .monitor.favicon import resolve_favicon
from .monitor.sitemap import fetch_all_pages
from .monitor.urlnorm import normalize_url
from .timeutil import utcnow


def run_basic_check(session: Session, competitor: Competitor) -> dict:
    """Sitemap diff: add / remove / restore / suspected. Mutates and commits the session."""
    pages = session.exec(
        select(Page).where(Page.competitor_id == competitor.id)
    ).all()
    page_by_normalized = {normalize_url(p.url): p for p in pages}
    active_by_normalized = {
        normalized: page
        for normalized, page in page_by_normalized.items()
        if page.status == "active"
    }
    old = {p.url: p.lastmod for p in active_by_normalized.values()}

    try:
        entries = fetch_all_pages(
            competitor.sitemap_url,
            timeout=settings.request_timeout,
            max_urls=settings.max_sitemap_urls,
        )
    except Exception as exc:  # noqa: BLE001
        competitor.status = "error"
        session.add(competitor)
        session.commit()
        return {
            "error": str(exc),
            "added": 0,
            "sitemap_removed": 0,
            "restored": 0,
            "suspected": 0,
        }

    entry_by_normalized = {}
    for entry in entries:
        entry_by_normalized.setdefault(normalize_url(entry.loc), entry)
    now = utcnow()
    changes = diff_pages(old, entries)

    # First crawl establishes a silent baseline: record the pages, but don't flood the
    # journal with one "added" entry per page — there's no change signal in the initial
    # inventory. Real adds/removes/edits get logged from the second crawl onward.
    is_baseline = competitor.last_checked_at is None
    logged = {"added": 0, "sitemap_removed": 0, "restored": 0, "suspected": 0}

    # Commit in batches so a big baseline (tens of thousands of pages) never holds the write
    # lock for the whole bulk insert — otherwise a concurrent "add competitor" gets stuck and
    # eventually fails with "database is locked".
    batch = max(1, settings.write_batch)
    pending = 0

    def commit_if_full():
        nonlocal pending
        if pending >= batch:
            session.commit()
            pending = 0

    for change in changes:
        normalized = normalize_url(change.url)
        entry = entry_by_normalized.get(normalized)
        if change.type == "added":
            page = page_by_normalized.get(normalized)
            if page is not None and page.status == "sitemap_removed":
                page.status = "active"
                page.lastmod = entry.lastmod if entry else None
                page.last_seen_at = now
                page.needs_detail_check = True
                session.add(page)
                session.add(
                    Change(
                        competitor_id=competitor.id,
                        page_id=page.id,
                        type="restored",
                        detail={"importance_score": 25},
                    )
                )
                logged["restored"] += 1
            else:
                page = Page(
                    competitor_id=competitor.id,
                    url=entry.loc if entry else change.url,
                    lastmod=entry.lastmod if entry else None,
                    needs_detail_check=True,
                )
                session.add(page)
                session.flush()
                page_by_normalized[normalized] = page
                if not is_baseline:
                    session.add(
                        Change(
                            competitor_id=competitor.id,
                            page_id=page.id,
                            type="added",
                            detail={"importance_score": 20},
                        )
                    )
                    logged["added"] += 1
        elif change.type == "sitemap_removed":
            page = active_by_normalized[normalized]
            page.status = "sitemap_removed"
            session.add(page)
            session.add(
                Change(
                    competitor_id=competitor.id,
                    page_id=page.id,
                    type="sitemap_removed",
                    detail={"importance_score": 20},
                )
            )
            logged["sitemap_removed"] += 1
        elif change.type == "suspected":
            page = active_by_normalized[normalized]
            page.lastmod = entry.lastmod if entry else None
            page.needs_detail_check = True
            session.add(page)
            session.add(
                Change(
                    competitor_id=competitor.id,
                    page_id=page.id,
                    type="suspected",
                    detail={**change.detail, "importance_score": 5},
                )
            )
            logged["suspected"] += 1
        pending += 1
        commit_if_full()

    for normalized, page in page_by_normalized.items():
        if normalized in entry_by_normalized and page.status == "active":
            page.last_seen_at = now
            session.add(page)
            pending += 1
            commit_if_full()

    competitor.status = "ok"
    competitor.last_checked_at = now
    if not competitor.favicon_url:  # resolve the site's declared favicon once
        competitor.favicon_url = resolve_favicon(competitor.sitemap_url)
    session.add(competitor)
    session.commit()

    return {"baseline": is_baseline, "tracked": len(entries), **logged}


def select_detailed_pages(session: Session, competitor_id: int, limit: int) -> list[Page]:
    """Select one rotating, priority-first detailed-crawl batch directly in SQL."""
    return list(
        session.exec(
            select(Page)
            .where(Page.competitor_id == competitor_id, Page.status == "active")
            .order_by(
                Page.needs_detail_check.desc(),
                Page.last_detailed_at.asc(),
                Page.id.asc(),
            )
            .limit(max(0, limit))
        ).all()
    )


def run_detailed_check(session: Session, competitor: Competitor) -> int:
    """Content-diff one priority/rotation batch. Returns number of modified pages."""
    from .monitor import fetch  # lazy: keep httpx out of service's import path

    pages = select_detailed_pages(session, competitor.id, settings.detailed_max_pages)
    modified = 0
    # One client for the whole run so connections (and per-host rate limiting) are reused
    # across pages instead of a fresh TCP/TLS handshake per page.
    with fetch.make_client(settings.request_timeout) as client:
        for page in pages:
            if check_page_content(session, page, client) is not None:
                modified += 1
            # Every attempt rotates to the back, including temporary failures. Successful
            # responses and 304s are therefore cleared as required, while failed pages still
            # come around again after the rest of the inventory gets a turn.
            page.last_detailed_at = utcnow()
            page.needs_detail_check = False
            session.add(page)
            session.commit()  # release the write lock between (network-bound) page checks
    return modified


def run_check(competitor_id: int) -> dict:
    """Full check for one competitor: basic always, detailed if opted in.

    run_basic_check / run_detailed_check commit their own work in batches (so the write lock
    is released frequently); the final commit here just flushes any straggler.
    """
    with Session(engine) as session:
        competitor = session.get(Competitor, competitor_id)
        if competitor is None:
            raise ValueError(f"competitor {competitor_id} not found")

        result = {"checked": competitor.name, **run_basic_check(session, competitor)}
        if competitor.detailed_on:
            result["modified"] = run_detailed_check(session, competitor)

        session.commit()
        return result
