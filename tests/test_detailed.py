"""SEO extraction, structured diffs, HTTP metadata, and deterministic importance."""
import os
import sys
import tempfile

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["FC_DB_URL"] = f"sqlite:///{tmp.name}"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.models import Change, Competitor, Page, Snapshot  # noqa: E402
from app.monitor import fetch  # noqa: E402
from app.config import settings  # noqa: E402
from app.monitor.detailed import check_page_content, extract_page_data  # noqa: E402


def html(*, title="Old title", description="Old description", h1="Old H1", canonical="/old", robots="index", body="Body"):
    return f"""<!doctype html><html><head>
      <title>{title}</title>
      <meta name="description" content="{description}">
      <link rel="alternate canonical" href="{canonical}">
      <meta name="ROBOTS" content="{robots}">
    </head><body><nav>Noise</nav><h1 hidden>Hidden H1</h1><h1>{h1}</h1>
      <main>{body}</main><script>noise()</script><footer>Noise</footer>
    </body></html>""".encode()


def response(content, *, status=200, url="https://example.test/page"):
    return httpx.Response(status, content=content, request=httpx.Request("GET", url))


def test_extract_page_data():
    data = extract_page_data(html())
    assert data.title == "Old title"
    assert data.meta_description == "Old description"
    assert data.h1 == "Old H1"
    assert data.canonical == "/old"
    assert data.robots == "index"
    assert data.visible_text == "Old H1\nBody"


def test_visible_text_is_bounded():
    original = settings.max_content_chars
    settings.max_content_chars = 10
    try:
        data = extract_page_data(html(body="x" * 200))
        assert len(data.visible_text) == 10
    finally:
        settings.max_content_chars = original


def test_structured_changes_and_importance():
    init_db()
    queued = []
    original_polite_get = fetch.polite_get
    fetch.polite_get = lambda *args, **kwargs: queued.pop(0)
    try:
        with Session(engine) as session:
            competitor = Competitor(name="Example", sitemap_url="https://example.test/sitemap.xml")
            session.add(competitor)
            session.commit()
            session.refresh(competitor)
            page = Page(competitor_id=competitor.id, url="https://example.test/page")
            session.add(page)
            session.commit()
            session.refresh(page)

            queued.append(response(html()))
            assert check_page_content(session, page, object()) is None
            session.commit()

            queued.append(response(html(title="New title")))
            title_change = check_page_content(session, page, object())
            session.commit()
            assert title_change.detail["seo_changes"] == {
                "title": {"from": "Old title", "to": "New title"}
            }
            assert title_change.detail["content_changed"] is False
            assert title_change.detail["importance_score"] == 75

            queued.append(response(html(title="New title", description="New description")))
            description_change = check_page_content(session, page, object())
            session.commit()
            assert set(description_change.detail["seo_changes"]) == {"meta_description"}
            assert description_change.detail["importance_score"] == 45

            queued.append(response(html(title="New title", description="New description", h1="New H1")))
            h1_change = check_page_content(session, page, object())
            session.commit()
            assert set(h1_change.detail["seo_changes"]) == {"h1"}
            assert h1_change.detail["content_changed"] is True
            assert h1_change.detail["importance_score"] == 100  # H1 70 + visible content 30

            queued.append(response(html(title="New title", description="New description", h1="New H1", canonical="/new")))
            canonical_change = check_page_content(session, page, object())
            session.commit()
            assert set(canonical_change.detail["seo_changes"]) == {"canonical"}
            assert canonical_change.detail["importance_score"] == 95

            queued.append(response(html(title="New title", description="New description", h1="New H1", canonical="/new", robots="noindex")))
            robots_change = check_page_content(session, page, object())
            session.commit()
            assert set(robots_change.detail["seo_changes"]) == {"robots"}
            assert robots_change.detail["importance_score"] == 100

            queued.append(response(html(title="New title", description="New description", h1="New H1", canonical="/new", robots="noindex"), url="https://example.test/plans"))
            redirect_change = check_page_content(session, page, object())
            session.commit()
            assert redirect_change.detail["seo_changes"] == {
                "final_url": {
                    "from": "https://example.test/page",
                    "to": "https://example.test/plans",
                }
            }
            assert redirect_change.detail["importance_score"] == 90

            queued.append(response(html(title="New title", description="New description", h1="New H1", canonical="/new", robots="noindex", body="Changed body"), url="https://example.test/plans"))
            content_change = check_page_content(session, page, object())
            session.commit()
            assert content_change.detail["seo_changes"] == {}
            assert content_change.detail["content_changed"] is True
            assert content_change.detail["importance_score"] == 30
            assert content_change.detail["hunks"]

            queued.append(response(html(title="New title", description="New description", h1="New H1", canonical="/new", robots="noindex", body="Changed body"), status=404, url="https://example.test/plans"))
            status_change = check_page_content(session, page, object())
            session.commit()
            assert status_change.detail["seo_changes"] == {
                "status_code": {"from": 200, "to": 404}
            }
            assert status_change.detail["importance_score"] == 90

            before = len(session.exec(select(Snapshot)).all())
            queued.append(response(html(title="New title", description="New description", h1="New H1", canonical="/new", robots="noindex", body="Changed body"), status=404, url="https://example.test/plans"))
            assert check_page_content(session, page, object()) is None
            session.commit()
            assert len(session.exec(select(Snapshot)).all()) == before
            assert len(session.exec(select(Change)).all()) == 8
            assert len(session.exec(select(Snapshot)).all()) == settings.snapshot_retention == 5
    finally:
        fetch.polite_get = original_polite_get


if __name__ == "__main__":
    try:
        test_extract_page_data()
        test_visible_text_is_bounded()
        test_structured_changes_and_importance()
        print("ok: SEO extraction, structured diffs, HTTP metadata, and importance")
    finally:
        os.unlink(tmp.name)
