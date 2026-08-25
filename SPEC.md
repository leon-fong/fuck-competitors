# Fuck Competitors Lightweight SEO Monitor

## 0. Project Context

Reference repository:

```text
https://github.com/michaelblaess/sitemap-tracker
```

The reference repository is for **design inspiration only**.

---

# 1. Product Goal

Turn `fuck-competitors` from:

```text
sitemap change monitor + full-text diff + AI/MCP analysis
```

into:

```text
lightweight self-hosted SEO competitor change monitor
```

The application should answer:

* What URLs did a competitor add to or remove from its sitemap?
* What important SEO fields changed on monitored pages?
* Did title, description, H1, canonical, robots or redirect destination change?
* What visible page content changed?
* Which changes are important enough to inspect?
* What pages changed recently?

The application must remain simple enough to self-host on:

```text
2 vCPU
2 GB RAM
small Debian/Ubuntu VPS
Docker Compose
```

---

# 2. Hard Constraints

These constraints are mandatory.

## Architecture

Keep:

```text
FastAPI
Jinja2
SQLite
SQLModel
APScheduler
httpx
selectolax
defusedxml
vanilla JS
Docker
```

Do not introduce:

```text
PostgreSQL
Redis
Celery
RabbitMQ
Kafka
React
Next.js
Vue
Playwright
Chromium
BeautifulSoup
Elasticsearch
external AI APIs
LLMs
vector databases
MCP
```

There must be:

```text
1 Docker container
1 Python process
1 Uvicorn worker
1 SQLite database
1 crawl worker globally
```

Sitemap remains the primary discovery mechanism.

Do NOT convert the application into a Screaming Frog style full-site crawler.

---

# 3. Explicitly Remove All AI Functionality

Remove all AI, MCP, Claude, Codex and ChatGPT integration from the product.

This is Milestone 0 and must happen before adding SEO functionality.

---

# Milestone 0 - Remove AI / MCP

## Goal

Return the project to a single lightweight web application.

## Delete

Delete:

```text
app/mcp_server.py
tests/test_mcp.py
```

## requirements.txt

Remove:

```text
mcp
```

Do not add any replacement AI dependency.

## docker-compose.yml

Remove the entire:

```yaml
mcp:
```

service.

Remove:

```text
9528
FC_MCP_TRANSPORT
FC_MCP_TOKEN
```

The final Compose stack must contain only:

```text
app
```

## Dockerfile

Change:

```text
EXPOSE 9527 9528
```

to:

```text
EXPOSE 9527
```

Keep:

```text
--workers 1
```

## app/config.py

Delete:

```text
mcp_transport
mcp_host
mcp_port
mcp_token
```

## Makefile

Update comments such as:

```text
app(:9527) + mcp(:9528)
```

to only refer to:

```text
app(:9527)
```

## Documentation

Remove all references to:

```text
AI analysis
MCP
Claude
Claude Code
Claude Desktop
Codex
ChatGPT connector
AI Agent
summarize_window
get_changes MCP tool
get_diff MCP tool
```

from:

```text
README.md
index.html
.env.example
Docker comments
CI configuration
```

Do not remove ordinary change-monitoring functionality.

## Verification

Repository-wide search for:

```text
mcp
MCP
Claude
Codex
ChatGPT
AI analysis
```

should return no product functionality related to AI.

Generic historical text should also be removed where practical.

## Acceptance Criteria

```text
docker compose up -d --build
```

starts exactly one container.

Only port:

```text
9527
```

is exposed.

Existing sitemap monitoring and content diff still work.

All non-MCP tests pass.

---

# Milestone 1 - Fix Page Lifecycle Semantics

## Goal

Make sitemap changes reliable before adding more SEO data.

Do not perform a major database redesign.

---

## 1.1 Rename "removed" meaning

Currently a URL disappearing from sitemap is treated like the page itself was removed.

That is too strong.

Change the event type:

```text
removed
```

to:

```text
sitemap_removed
```

Meaning:

> URL disappeared from the competitor sitemap.

Do NOT imply that the HTTP page is 404 or deleted.

UI label:

```text
移出 Sitemap
```

or English equivalent:

```text
Removed from sitemap
```

Keep the database `Page.status` concept simple.

Allowed:

```text
active
sitemap_removed
```

Do not introduce a complex state machine.

---

## 1.2 Handle URLs that return to sitemap

If:

```text
/pricing
```

was previously marked `sitemap_removed`, and later appears again:

DO NOT create a second `Page`.

Reuse the existing Page row.

Change:

```text
status = active
```

Create event:

```text
restored
```

Meaning:

```text
URL returned to sitemap
```

Historical content and snapshots must remain attached to the same Page ID.

---

## 1.3 Conservative URL normalization

Add:

```text
app/monitor/urlnorm.py
```

Implement only safe normalization:

```text
lowercase scheme
lowercase hostname
remove URL fragment
remove default :80 for http
remove default :443 for https
empty path -> /
```

Do NOT:

```text
remove query strings
sort query strings
strip arbitrary trailing slashes
remove tracking parameters
guess canonical URLs
```

Avoid over-normalization.

Use the normalized form when comparing sitemap URLs.

Store the original discovered URL for display and fetching.

Do not build a complicated canonical URL subsystem.

---

## Tests

Add tests for:

```text
removed -> sitemap_removed
sitemap_removed -> restored
restored URL keeps same Page ID
fragment normalization
hostname normalization
default port normalization
query string preservation
```

## Acceptance Criteria

Repeated removal/restoration of one URL never creates duplicate page histories.

---

# Milestone 2 - Lightweight SEO Snapshot

## Goal

Borrow the useful idea from `sitemap-tracker`:

> Extract SEO metadata from HTML that has already been downloaded.

Do NOT create additional HTTP requests just for SEO metadata.

Do NOT add BeautifulSoup.

Use existing:

```text
selectolax
```

---

# 2.1 Expand Snapshot

Extend the existing `Snapshot` model.

Keep:

```text
content_hash
title
content_text
captured_at
```

Add:

```text
meta_description: Optional[str]

h1: Optional[str]

canonical: Optional[str]

robots: Optional[str]

status_code: Optional[int]

final_url: Optional[str]
```

That is all for this milestone.

Do NOT add:

```text
OpenGraph
Twitter Cards
hreflang
JSON-LD
schema.org parser
H2-H6 arrays
keyword density
tech stack detection
screenshots
Core Web Vitals
```

Those are intentionally out of scope.

---

# 2.2 Replace extract_text()

Refactor:

```text
extract_text()
```

into something like:

```text
extract_page_data()
```

Return a small structure containing:

```text
title
meta_description
h1
canonical
robots
visible_text
```

Use selectolax selectors.

Suggested extraction rules:

```text
title
    <title>

meta_description
    meta[name="description"]

h1
    first visible <h1>

canonical
    link[rel="canonical"]

robots
    meta[name="robots"]

visible_text
    existing normalized body text logic
```

Continue removing high-noise elements from visible text:

```text
script
style
noscript
svg
```

Keep the current behavior for:

```text
nav
header
footer
```

for now.

Do NOT add internal-link graph monitoring in this version.

That can be considered later if real usage proves it necessary.

---

# 2.3 Record HTTP information

The existing httpx client already follows redirects.

For every detailed page fetch, record:

```text
status_code = final response status
final_url = str(response.url)
```

This allows detecting:

```text
/pricing
-> /plans
```

without implementing a redirect graph.

Do not store full redirect chains yet.

---

# Milestone 3 - Structured SEO Change Detection

## Goal

Keep the existing `Change(type="modified")` architecture.

Do NOT create ten new database event types.

Instead, enrich:

```text
Change.detail
```

---

## 3.1 SEO field diff

Compare the latest Snapshot to the previous Snapshot.

Detect changes to:

```text
title
meta_description
h1
canonical
robots
status_code
final_url
```

Store:

```json
{
  "seo_changes": {
    "title": {
      "from": "Old title",
      "to": "New title"
    },
    "canonical": {
      "from": "https://example.com/a",
      "to": "https://example.com/b"
    }
  }
}
```

Only changed fields should be included.

---

## 3.2 Content diff

Keep the existing:

```text
content_hash
line diff
diff hunks
```

Do not replace it.

A modified Change should be created when:

```text
content changed
OR
SEO field changed
OR
HTTP/final URL changed
```

This means a title-only change must still create a `modified` event.

---

# 3.3 Importance Score

Add a deterministic score.

No AI.

No machine learning.

Suggested weights:

```text
robots changed             100
canonical changed           95
final_url changed           90
status_code changed         90

title changed               75
h1 changed                  70

meta description changed    45

visible content changed     30

sitemap restored            25
sitemap added               20
sitemap removed             20

lastmod-only suspected       5
```

Cap:

```text
0-100
```

Store:

```text
importance_score
```

inside `Change.detail`.

Do not add another database column unless clearly necessary.

UI labels:

```text
90-100  Critical
70-89   High
40-69   Medium
0-39    Low
```

This replaces any need for AI summarization.

---

# Milestone 4 - VPS-Friendly Crawl Scheduling

## Goal

Fix the current detailed-crawl starvation issue while reducing resource usage.

Current behavior must NOT continue as:

```text
load every active page
take first N
```

because the same pages can be repeatedly selected.

---

# 4.1 Add two Page fields

Add:

```text
last_detailed_at: Optional[datetime]
needs_detail_check: bool = False
```

Use the existing lightweight migration function in:

```text
app/db.py
```

Do not introduce Alembic.

---

# 4.2 Mark priority pages

When a page is:

```text
newly added
restored
lastmod suspected changed
```

set:

```text
needs_detail_check = True
```

---

# 4.3 Select detailed pages directly in SQL

Do NOT:

```python
pages = query.all()
pages = pages[:limit]
```

Instead query only the required rows.

Conceptually:

```text
ORDER BY
needs_detail_check DESC,
last_detailed_at ASC

LIMIT FC_DETAILED_MAX_PAGES
```

Null `last_detailed_at` means never inspected and should naturally receive priority.

This creates a simple rotating crawl without introducing a queue table.

---

# 4.4 After a crawl attempt

Update:

```text
last_detailed_at = now
```

After the page has been attempted.

Set:

```text
needs_detail_check = False
```

after a successful request or 304.

For temporary network failures, avoid retry loops that permanently starve the rest of the queue.

A failed page should eventually rotate back into the queue, but it must not be retried continuously.

Keep this implementation simple.

---

# 4.5 VPS defaults

Change defaults to:

```text
FC_DEFAULT_INTERVAL_HOURS=24

FC_DETAILED_MAX_PAGES=100

FC_SNAPSHOT_RETENTION=5

FC_CRAWL_DELAY_SECONDS=1.0

FC_REQUEST_TIMEOUT=15
```

Keep:

```text
FC_MAX_SITEMAP_URLS=50000
```

because parsing sitemap XML is much cheaper than downloading 50,000 HTML pages.

Detailed monitoring remains:

```text
OFF by default
```

per competitor.

---

# 4.6 Serialize all crawl jobs

Configure APScheduler with:

```text
max_workers = 1
```

globally.

Only one competitor crawl may execute at a time.

Reason:

```text
2 CPU
2 GB RAM
SQLite single writer
```

If three competitors become due simultaneously:

```text
competitor A
then competitor B
then competitor C
```

They should queue instead of running concurrently.

Keep:

```text
coalesce=True
max_instances=1
```

for each scheduled competitor.

---

# Milestone 5 - Storage and Memory Protection

## Goal

Prevent unusual competitor pages from consuming excessive memory or SQLite storage.

Do not build a complicated streaming crawler.

---

# 5.1 Content text limit

Add config:

```text
FC_MAX_CONTENT_CHARS=100000
```

After extracting normalized visible text:

```python
text = text[:settings.max_content_chars]
```

The hash and diff should operate on this bounded text.

This is enough for competitor monitoring.

The application does not need to archive complete websites.

---

# 5.2 Snapshot retention

Keep at most:

```text
5 snapshots per page
```

by default.

Do not retain unchanged snapshots.

Existing behavior where an unchanged content hash does not create another snapshot should remain.

---

# 5.3 Do not load unnecessary database rows

Review new code for `.all()` calls.

For detailed crawling:

```text
SELECT only the limited pages required.
```

For UI lists:

use existing pagination/filtering behavior where possible.

Do not implement a generic caching system.

---

# Milestone 6 - Minimal UI Upgrade

## Goal

Expose the new SEO information without redesigning the application.

Keep the existing visual language and Jinja architecture.

---

# 6.1 Change log

Each modified change should display small badges when applicable:

```text
TITLE
H1
DESCRIPTION
CANONICAL
ROBOTS
REDIRECT
CONTENT
```

Example:

```text
/pricing

High · 82

TITLE
H1
CONTENT
```

---

# 6.2 Diff drawer

Above the existing text diff, add:

```text
SEO changes
```

Example:

```text
Title

- Pricing | Acme
+ AI Pricing | Acme


H1

- Plans for every team
+ AI agents for every team


Canonical

unchanged
```

Only show changed fields.

Do not show unchanged values.

Then show the existing content diff underneath.

---

# 6.3 Filters

If easy to implement within the current UI, add:

```text
Importance:
All
Critical
High
Medium
Low
```

This is optional for Milestone 6.

Do not add complex dashboard charts yet.

---

# 6.4 Competitor card

Keep:

```text
tracked page count
last checked
detailed monitoring toggle
```

Optionally add:

```text
High-impact changes in last 7 days
```

Do not add graphs yet.

---

# Milestone 7 - Tests and Hardening

## Required tests

Keep existing tests and add coverage for:

### Sitemap lifecycle

```text
added
sitemap_removed
restored
suspected
```

### SEO extraction

Test HTML containing:

```text
title
description
H1
canonical
robots
```

### SEO diff

Test:

```text
title-only change
description-only change
canonical-only change
robots noindex change
final URL change
content-only change
no change
```

### Scheduler / page selection

Test that:

```text
priority pages selected first
never-checked pages selected before recently checked pages
query returns no more than detailed_max_pages
```

### Snapshot retention

Test:

```text
no more than configured snapshot count remains
```

### Reappearing URL

Verify the same page database ID survives:

```text
active
-> sitemap_removed
-> restored
```

---

# 8. Explicitly Out of Scope

Do NOT implement any of the following during these milestones:

```text
AI summaries
LLM integrations
MCP
OpenAI
Anthropic
Claude
Codex

Playwright
Chromium
screenshots
JS rendering

internal link graph
backlink analysis
keyword rankings
Google Search Console
Google Analytics
Ahrefs API
Semrush API

tech stack detection
CMS detection

hreflang monitoring
JSON-LD/schema diff
OpenGraph diff

PostgreSQL
Redis
Celery

email alerts
Slack alerts
Telegram alerts

user accounts
multi-tenancy
billing

React/Vue frontend
```

These features can only be considered after the lightweight monitoring core proves useful.

---

# 9. Expected Final Architecture

```text
                 Sitemap
                    |
                    v
              Sitemap parser
                    |
                    v
               URL inventory
                    |
          +---------+----------+
          |                    |
          v                    v
    Sitemap diff        Detailed queue
                               |
                         max 100/run
                               |
                               v
                            httpx
                               |
                  +------------+-------------+
                  |            |             |
                  v            v             v
                HTTP        SEO fields    Visible text
                  |            |             |
                  +------------+-------------+
                               |
                               v
                         Snapshot diff
                               |
                               v
                         Change record
                               |
                               v
                       Importance score
                               |
                               v
                         Web interface
```

No AI layer.

No secondary service.

---

# 10. Expected Runtime Topology

```text
Docker
└── fuck-competitors
    ├── FastAPI
    ├── APScheduler
    │   └── crawl executor max_workers=1
    ├── httpx
    └── SQLite WAL
```

Only:

```text
9527/tcp
```

needs to exist.

---

# 11. Resource Target

For normal idle operation on a small VPS, target:

```text
RAM:
prefer < 200 MB idle

CPU:
near 0% idle

Docker containers:
1

Uvicorn workers:
1

Concurrent competitor crawls:
1

Detailed HTML requests:
100 maximum per scheduled run by default
```

Do not artificially reserve large Docker memory amounts.

The application should fail gracefully if one competitor is temporarily unavailable.

---

# 12. Configuration After Completion

Expected `.env.example`:

```env
FC_DB_URL=sqlite:////data/app.db

FC_DEFAULT_INTERVAL_HOURS=24

FC_REQUEST_TIMEOUT=15

FC_MAX_SITEMAP_URLS=50000

FC_DETAILED_MAX_PAGES=100

FC_SNAPSHOT_RETENTION=5

FC_MAX_CONTENT_CHARS=100000

FC_WRITE_BATCH=200

FC_RESPECT_ROBOTS=true

FC_CRAWL_DELAY_SECONDS=1.0

FC_BLOCK_COOLDOWN_SECONDS=900
```

There must be no:

```text
FC_MCP_*
FC_AI_*
OPENAI_*
ANTHROPIC_*
```

configuration.

---

# 13. Recommended Implementation Order

Implement strictly in this order:

```text
M0 Remove MCP / AI
        |
M1 Page lifecycle correctness
        |
M2 Lightweight SEO snapshot
        |
M3 Structured SEO diff + score
        |
M4 Resource-aware crawl scheduling
        |
M5 Storage / memory limits
        |
M6 Minimal UI
        |
M7 Tests + cleanup
```

Do not combine all milestones into one large refactor.

Each milestone must leave the application runnable.

---

# 14. Commit Strategy

Recommended commits:

```text
refactor: remove MCP and AI integration

fix: preserve page history across sitemap removal and restore

feat: capture lightweight SEO metadata in page snapshots

feat: detect structured SEO changes and score importance

perf: rotate detailed crawling with bounded page selection

perf: serialize crawl jobs for low-memory deployments

feat: surface SEO changes in the existing UI

test: cover SEO monitoring and page lifecycle
```

Do not add agent names as commit co-authors.

---

# 15. Definition of Done

The project is complete when:

1. `docker compose up -d --build` starts one container.
2. Only port 9527 is exposed.
3. No AI/MCP functionality remains.
4. Existing sitemap monitoring still works.
5. Added and sitemap-removed pages are detected.
6. Removed pages can return without losing history.
7. Detailed monitoring captures:

   * title
   * meta description
   * H1
   * canonical
   * robots
   * HTTP status
   * final URL
   * visible text
8. SEO-only changes create `modified` events.
9. Changes receive deterministic importance scores.
10. Detailed crawling rotates pages instead of repeatedly crawling the same first N URLs.
11. Only one competitor crawl runs at once.
12. Detailed crawling defaults to 100 HTML pages per scheduled run.
13. Snapshot content is bounded.
14. Snapshot retention defaults to five.
15. Existing UI remains recognizable.
16. No new infrastructure service is required.
17. All tests pass.
18. The project remains suitable for a 2C/2GB VPS.

---

# 16. Development Principle

When choosing between:

```text
more features
```

and:

```text
simpler architecture
```

choose simpler architecture.

The project should remain primarily:

> a sitemap-driven competitor change monitor with lightweight SEO awareness.

It should NOT evolve into:

> a full technical SEO crawler, enterprise observability platform, or AI agent system.

Use ideas from `michaelblaess/sitemap-tracker` only where they directly improve the quality of competitor change signals without significantly increasing CPU, memory, dependencies or operational complexity.
