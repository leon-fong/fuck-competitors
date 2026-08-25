"""Shape raw DB rows into the structures the templates iterate over."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from .models import Change, Competitor, Page

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
GLYPH = {
    "added": "＋",
    "sitemap_removed": "－",
    "restored": "↺",
    "modified": "±",
    "suspected": "±",
}
GTYPE = {
    "added": "add",
    "sitemap_removed": "del",
    "restored": "add",
    "modified": "mod",
    "suspected": "susp",
}


def monogram(name: str) -> str:
    return (name.strip()[:1] or "?").upper()


def interval_label(hours: int) -> str:
    if hours == 24:
        return "每天"
    if hours == 168:
        return "每周"
    return f"每 {hours} 小时"


def url_path(url: str) -> str:
    p = urlparse(url)
    return (p.path or "/") + (f"?{p.query}" if p.query else "")


def host_of(url: str) -> str:
    return urlparse(url).netloc


def favicon_url_for(competitor) -> str:
    """Prefer the site's resolved <link rel=icon>; else its /favicon.ico (the UI falls back
    to a letter monogram if even that 404s)."""
    if getattr(competitor, "favicon_url", None):
        return competitor.favicon_url
    host = host_of(competitor.sitemap_url)
    return f"https://{host}/favicon.ico" if host else ""


def weekday_cn(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def day_label(d: date, today: date) -> str:
    if d == today:
        return "今天"
    if d == today - timedelta(days=1):
        return "昨天"
    return f"{d.month} 月 {d.day} 日"


def _note(change: Change) -> str:
    if change.type == "added":
        return "加入 Sitemap"
    if change.type == "suspected":
        det = change.detail or {}
        return f"lastmod {det.get('lastmod_from') or '—'} → {det.get('lastmod_to') or '—'}，可能已修改"
    if change.type == "modified":
        detail = change.detail or {}
        fields = list((detail.get("seo_changes") or {}).keys())
        if detail.get("content_changed"):
            fields.append("content")
        return "、".join(field.upper() for field in fields) or "页面信息变化"
    if change.type == "sitemap_removed":
        return "移出 Sitemap"
    if change.type == "restored":
        return "重新加入 Sitemap"
    return ""


def importance_label(score: int) -> str:
    if score >= 90:
        return "Critical"
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def importance_band(score: int) -> str:
    return importance_label(score).lower()


def _seo_badges(change: Change) -> list[str]:
    if change.type != "modified":
        return []
    detail = change.detail or {}
    changed = detail.get("seo_changes") or {}
    badges = []
    for field, label in (
        ("title", "TITLE"),
        ("h1", "H1"),
        ("meta_description", "DESCRIPTION"),
        ("canonical", "CANONICAL"),
        ("robots", "ROBOTS"),
        ("final_url", "REDIRECT"),
    ):
        if field in changed:
            badges.append(label)
    if detail.get("content_changed"):
        badges.append("CONTENT")
    return badges


def _dominant(summary: dict) -> str:
    if summary["modified"] or summary["suspected"]:
        return "mod"
    if summary["sitemap_removed"]:
        return "del"
    return "add"


def _row_vm(change: Change, page: Page | None) -> dict:
    score = int((change.detail or {}).get("importance_score", 0))
    return {
        "id": change.id,
        "type": change.type,
        "gtype": GTYPE[change.type],
        "glyph": GLYPH[change.type],
        "path": url_path(page.url) if page else "—",
        "note": _note(change),
        "suspected": change.type == "suspected",
        "importance_score": score,
        "importance_label": importance_label(score),
        "importance_band": importance_band(score),
        "seo_badges": _seo_badges(change),
    }


def group_changes(
    changes: list[Change],
    comp_by_id: dict[int, Competitor],
    page_by_id: dict[int, Page],
    today: date,
) -> list[dict]:
    """changes must be ordered newest-first. Groups by day, then by competitor."""
    days: "OrderedDict[date, OrderedDict[int, list]]" = OrderedDict()
    for ch in changes:
        d = ch.detected_at.date()
        days.setdefault(d, OrderedDict()).setdefault(ch.competitor_id, []).append(ch)

    groups = []
    for d, by_comp in days.items():
        entries = []
        day_total = 0
        for cid, rows in by_comp.items():
            comp = comp_by_id.get(cid)
            summary = {
                "added": 0,
                "sitemap_removed": 0,
                "restored": 0,
                "modified": 0,
                "suspected": 0,
            }
            row_vms = []
            for ch in rows:
                summary[ch.type] += 1
                day_total += 1
                row_vms.append(_row_vm(ch, page_by_id.get(ch.page_id)))
            entries.append(
                {
                    "name": comp.name if comp else "—",
                    "monogram": monogram(comp.name) if comp else "?",
                    "color": comp.color if comp else "#39332B",
                    "favicon": favicon_url_for(comp) if comp else "",
                    "summary": summary,
                    "rows": row_vms,
                    "dominant": _dominant(summary),
                    "time": rows[0].detected_at.strftime("%H:%M"),
                }
            )
        groups.append(
            {"label": day_label(d, today), "weekday": weekday_cn(d), "count": day_total, "entries": entries}
        )
    return groups


def overview_stats(recent: list[Change], site_count: int, page_count: int) -> dict:
    added = sum(1 for c in recent if c.type == "added")
    removed = sum(1 for c in recent if c.type == "sitemap_removed")
    restored = sum(1 for c in recent if c.type == "restored")
    modified = sum(1 for c in recent if c.type in ("modified", "suspected"))
    return {
        "added": added,
        "removed": removed,
        "restored": restored,
        "modified": modified,
        "sites": site_count,
        "pages": page_count,
        "total": added + removed + restored + modified,
    }


def build_detail_vm(change: Change, page: Page | None, competitor: Competitor | None) -> dict:
    dt = change.detected_at.strftime("%Y/%m/%d %H:%M")
    detail = change.detail or {}
    importance_score = int(detail.get("importance_score", 0))
    vm = {
        "change_id": change.id,
        "page_id": page.id if page else None,
        "competitor_id": competitor.id if competitor else None,
        "site": competitor.name if competitor else "—",
        "path": url_path(page.url) if page else "—",
        "full_url": page.url if page else "#",
        "glyph": GLYPH[change.type],
        "gtype": GTYPE[change.type],
        "suspected": change.type == "suspected",
        "mode": "none",
        "meta": [],
        "importance_score": importance_score,
        "importance_label": importance_label(importance_score),
    }

    if change.type == "added":
        vm["title"] = "新增页面"
        vm["mode"] = "newpage"
        vm["snapshot"] = {"title": detail.get("title") or "新加入 sitemap 的页面", "url": page.url if page else "#"}
        vm["meta"] = [("检测时间", dt), ("加入监控", page.first_seen_at.strftime("%Y-%m-%d") if page else "—")]
    elif change.type == "sitemap_removed":
        vm["title"] = "移出 Sitemap"
        vm["mode"] = "gone"
        vm["snapshot"] = {"title": "已从 sitemap 移除", "url": page.url if page else "#"}
        vm["meta"] = [("检测时间", dt), ("状态", "移出 Sitemap"), ("最后可见", page.last_seen_at.strftime("%Y-%m-%d") if page else "—")]
    elif change.type == "restored":
        vm["title"] = "重新加入 Sitemap"
        vm["mode"] = "restored"
        vm["snapshot"] = {"title": "URL 已恢复监控", "url": page.url if page else "#"}
        vm["meta"] = [("检测时间", dt), ("状态", "已恢复"), ("首次发现", page.first_seen_at.strftime("%Y-%m-%d") if page else "—")]
    elif change.type == "modified":
        vm["title"] = detail.get("title") or "内容已修改"
        vm["mode"] = "diff"
        vm["hunks"] = detail.get("hunks", [])
        vm["seo_changes"] = detail.get("seo_changes", {})
        vm["content_changed"] = bool(detail.get("content_changed"))
        vm["meta"] = [("检测时间", dt), ("重要程度", f"{vm['importance_label']} · {importance_score}"), ("监控深度", "详细")]
    elif change.type == "suspected":
        vm["title"] = "页面可能已修改"
        vm["mode"] = "suspected"
        vm["lastmod"] = f"{detail.get('lastmod_from') or '—'} → {detail.get('lastmod_to') or '—'}"
        vm["meta"] = [("检测时间", dt), ("lastmod", vm["lastmod"]), ("监控深度", "基础")]

    return vm
