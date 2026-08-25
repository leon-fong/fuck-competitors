"""Detailed crawl selection rotates in SQL and respects VPS limits."""
import os
import sys
import tempfile
from contextlib import nullcontext
from datetime import timedelta

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["FC_DB_URL"] = f"sqlite:///{tmp.name}"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select  # noqa: E402

import app.service as service  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Competitor, Page  # noqa: E402
from app.monitor import fetch  # noqa: E402
from app.scheduler import scheduler  # noqa: E402
from app.timeutil import utcnow  # noqa: E402


def _page(session, competitor, path, *, priority=False, checked=None):
    page = Page(
        competitor_id=competitor.id,
        url=f"https://example.test/{path}",
        needs_detail_check=priority,
        last_detailed_at=checked,
    )
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


def test_priority_rotation_and_limit():
    init_db()
    now = utcnow()
    with Session(engine) as session:
        competitor = Competitor(name="Example", sitemap_url="https://example.test/sitemap.xml")
        session.add(competitor)
        session.commit()
        session.refresh(competitor)

        priority_old = _page(session, competitor, "priority-old", priority=True, checked=now - timedelta(days=3))
        priority_recent = _page(session, competitor, "priority-recent", priority=True, checked=now)
        never_checked = _page(session, competitor, "never")
        recently_checked = _page(session, competitor, "recent", checked=now - timedelta(hours=1))
        _page(session, competitor, "extra", checked=now)

        selected = service.select_detailed_pages(session, competitor.id, 4)
        assert [page.id for page in selected] == [
            priority_old.id,
            priority_recent.id,
            never_checked.id,
            recently_checked.id,
        ]
        assert len(service.select_detailed_pages(session, competitor.id, 2)) == 2


def test_attempts_rotate_even_after_failure():
    original_limit = settings.detailed_max_pages
    original_make_client = fetch.make_client
    original_check = service.check_page_content
    attempted = []
    try:
        settings.detailed_max_pages = 3
        fetch.make_client = lambda *args, **kwargs: nullcontext(object())
        service.check_page_content = lambda session, page, client: attempted.append(page.id) or None

        with Session(engine) as session:
            competitor = session.exec(select(Competitor)).first()
            selected_ids = [
                page.id
                for page in service.select_detailed_pages(
                    session, competitor.id, settings.detailed_max_pages
                )
            ]
            service.run_detailed_check(session, competitor)
            assert attempted == selected_ids
            for page_id in selected_ids:
                page = session.get(Page, page_id)
                assert page.last_detailed_at is not None
                assert page.needs_detail_check is False
    finally:
        settings.detailed_max_pages = original_limit
        fetch.make_client = original_make_client
        service.check_page_content = original_check


def test_vps_defaults_and_single_scheduler_worker():
    assert settings.default_interval_hours == 24
    assert settings.detailed_max_pages == 100
    assert settings.snapshot_retention == 5
    assert settings.crawl_delay_seconds == 1.0
    assert settings.request_timeout == 15
    assert settings.max_sitemap_urls == 50_000
    assert settings.max_content_chars == 100_000
    assert scheduler._executors["default"]._pool._max_workers == 1


if __name__ == "__main__":
    try:
        test_priority_rotation_and_limit()
        test_attempts_rotate_even_after_failure()
        test_vps_defaults_and_single_scheduler_worker()
        print("ok: priority rotation, SQL limit, attempt state, and VPS defaults")
    finally:
        os.unlink(tmp.name)
