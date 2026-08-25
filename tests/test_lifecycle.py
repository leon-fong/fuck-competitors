"""A URL removed from and restored to a sitemap keeps one Page history."""
import os
import sys
import tempfile

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["FC_DB_URL"] = f"sqlite:///{tmp.name}"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select  # noqa: E402

import app.service as service  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Change, Competitor, Page  # noqa: E402
from app.monitor.sitemap import PageEntry  # noqa: E402


def test_remove_restore_reuses_page_id():
    init_db()
    current = [[PageEntry("HTTPS://Example.COM:443/pricing?plan=pro#top")]]
    service.fetch_all_pages = lambda *args, **kwargs: current[0]
    service.resolve_favicon = lambda *args, **kwargs: None

    with Session(engine) as session:
        competitor = Competitor(name="Example", sitemap_url="https://example.com/sitemap.xml")
        session.add(competitor)
        session.commit()
        session.refresh(competitor)

        service.run_basic_check(session, competitor)
        page = session.exec(select(Page)).one()
        original_id = page.id
        original_url = page.url
        assert page.needs_detail_check is True

        current[0] = []
        removed = service.run_basic_check(session, competitor)
        session.refresh(page)
        assert removed["sitemap_removed"] == 1
        assert page.status == "sitemap_removed"

        current[0] = [PageEntry("https://example.com/pricing?plan=pro#details")]
        restored = service.run_basic_check(session, competitor)
        session.refresh(page)
        assert restored["restored"] == 1
        assert page.status == "active"
        assert page.id == original_id
        assert page.url == original_url  # original discovered URL remains the fetch/display URL
        assert page.needs_detail_check is True

        # Repeat the cycle to guard against histories forking on later restorations.
        current[0] = []
        service.run_basic_check(session, competitor)
        current[0] = [PageEntry("https://EXAMPLE.com:443/pricing?plan=pro")]
        service.run_basic_check(session, competitor)
        session.refresh(page)

        pages = session.exec(select(Page)).all()
        changes = session.exec(select(Change).order_by(Change.id)).all()
        assert len(pages) == 1
        assert page.id == original_id and page.status == "active"
        assert [change.type for change in changes] == [
            "sitemap_removed",
            "restored",
            "sitemap_removed",
            "restored",
        ]
        assert {change.page_id for change in changes} == {original_id}
        assert [change.detail["importance_score"] for change in changes] == [20, 25, 20, 25]


def test_legacy_removed_rows_are_migrated():
    with Session(engine) as session:
        competitor = session.exec(select(Competitor)).first()
        legacy = Page(
            competitor_id=competitor.id,
            url="https://example.com/legacy",
            status="removed",
        )
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        event = Change(competitor_id=competitor.id, page_id=legacy.id, type="removed")
        session.add(event)
        session.commit()
        legacy_id, event_id = legacy.id, event.id

    init_db()
    with Session(engine) as session:
        assert session.get(Page, legacy_id).status == "sitemap_removed"
        assert session.get(Change, event_id).type == "sitemap_removed"


if __name__ == "__main__":
    try:
        test_remove_restore_reuses_page_id()
        test_legacy_removed_rows_are_migrated()
        print("ok: sitemap removal/restoration preserves one Page ID")
    finally:
        os.unlink(tmp.name)
