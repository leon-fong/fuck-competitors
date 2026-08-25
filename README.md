<div align="center">

# Fuck Competitors

**轻量、自托管的 SEO 竞品变化监控。**

[![CI](https://github.com/leon-fong/fuck-competitors/actions/workflows/ci.yml/badge.svg)](https://github.com/leon-fong/fuck-competitors/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)

填入竞品的 `sitemap.xml`，应用会定期记录 URL 加入、移出或恢复 Sitemap，以及页面 SEO 字段、
HTTP 状态、重定向目标和可见正文的变化。

</div>

## 当前产品边界

这是一个面向小型 VPS 的 Sitemap-first 监控器，不是全站爬虫或网站归档系统。

- Sitemap 是唯一的页面发现入口；不会递归跟随页面链接扫描整站。
- 详细监控按竞品开启，默认关闭。
- 不执行 JavaScript，不使用浏览器、Playwright、Chromium 或截图。
- 不包含 AI、LLM、MCP、Claude、Codex、ChatGPT、OpenAI 或 Anthropic 集成。
- 不调用外部 AI API，不需要 API key，也不会把页面内容发送给 AI 服务。
- 不依赖 PostgreSQL、Redis、Celery、消息队列或搜索集群。

当前运行时固定为：

```text
1 Docker container
1 Python process
1 Uvicorn worker
1 SQLite database
1 global crawl worker
1 exposed port: 9527
```

推荐资源：`2 vCPU / 2 GB RAM / Debian 或 Ubuntu / Docker Compose`。

## 界面截图

| 最近动态 | 变更日志 |
| --- | --- |
| ![最近动态](docs/screenshots/overview.png) | ![变更日志](docs/screenshots/changelog.png) |
| **内容 diff** | **竞品列表** |
| ![内容 diff](docs/screenshots/diff-drawer.png) | ![竞品列表](docs/screenshots/sites.png) |

## 功能

- **Sitemap 生命周期**：记录 `added`、`sitemap_removed`、`restored` 和 lastmod `suspected`。
- **保守 URL 身份比较**：只规范 scheme、hostname、默认端口、fragment 和空路径；保留 query 与尾斜杠。
- **SEO 快照**：Title、Description、首个可见 H1、Canonical、Robots、HTTP 状态和最终 URL。
- **正文 diff**：对去噪、规范化且有长度上限的可见正文生成逐行 hunks。
- **重要程度**：完全确定性的 0–100 评分，无 AI 或机器学习。
- **轮转抓取**：优先新增、恢复和 lastmod 变化的页面，再选择最久未详细检查的页面。
- **轻量 UI**：服务端 Jinja2、原生 JavaScript、SEO badges、抽屉详情和重要程度筛选。
- **安全持久化**：SQLite WAL、写锁等待、分批提交、快照保留和主机目录挂载。

## 从旧版本到当前版本：Milestone 0–7

这部分是完整的实现记录，方便维护者、自动化 Agent 和升级旧部署的人理解为什么代码现在是这样。

### Milestone 0：移除 AI / MCP

旧版本的第二个 MCP 服务和 AI 分析功能已经完全删除：

- 删除 MCP server 与对应测试。
- 删除 `mcp` Python 依赖。
- 删除 MCP transport、host、port、token 配置。
- 删除 Compose 中的第二个服务和 `9528` 端口。
- 删除 Claude、Codex、ChatGPT connector、AI summary 等产品功能。
- Docker 现在只运行 `app`，只暴露 `9527`，仍使用一个 Uvicorn worker。

因此部署不需要 MCP client、AI provider、API key、token 或第二个容器。AI/MCP 旧客户端也无法再连接，
因为相关端点、配置和端口已经不存在。

### Milestone 1：可靠的页面生命周期

- URL 从 Sitemap 消失时记录 `sitemap_removed`，只表示“移出 Sitemap”，不声称 HTTP 页面已删除或 404。
- URL 再次出现时复用原 `Page.id`，状态恢复为 `active` 并记录 `restored`。
- 历史 Snapshot 与 Change 始终挂在同一个 Page 上，反复移出/恢复不会生成重复历史。
- 启动迁移会把旧数据库中的 Page status 和 Change type `removed` 改为 `sitemap_removed`。
- `app/monitor/urlnorm.py` 仅执行以下安全规范化：

```text
lowercase scheme
lowercase hostname
remove fragment
remove http :80
remove https :443
empty path -> /
```

Query string 不删除、不排序；普通尾斜杠不删除；不会猜测 canonical。数据库仍保存首次发现的原始 URL，
用于显示和抓取，规范化结果只用于 Sitemap 身份比较。

### Milestone 2：轻量 SEO Snapshot

每次已经发生的详细 HTML 下载会同时提取：

```text
title
meta_description
h1
canonical
robots
visible_text
status_code
final_url
```

解析器是 `selectolax`。提取过程不会为 SEO 字段增加额外页面请求；httpx 已跟随重定向，最终响应 URL
直接保存为 `final_url`。正文继续移除 `script`、`style`、`noscript`、`svg`、`nav`、`header`、
`footer` 和静态隐藏元素。

### Milestone 3：结构化变化与评分

详细监控比较最新两个 Snapshot。以下任一条件成立就记录一个 `Change(type="modified")`：

```text
visible content changed
SEO field changed
HTTP status changed
final URL changed
```

`Change.detail` 保存结构化变化：

```json
{
  "seo_changes": {
    "title": {"from": "Old title", "to": "New title"},
    "canonical": {"from": "https://example.com/a", "to": "https://example.com/b"}
  },
  "content_changed": true,
  "hunks": [],
  "importance_score": 100
}
```

评分是各项权重相加后封顶 100：

| 变化 | 分值 |
| --- | ---: |
| Robots | 100 |
| Canonical | 95 |
| Final URL | 90 |
| HTTP status | 90 |
| Title | 75 |
| H1 | 70 |
| Meta description | 45 |
| Visible content | 30 |
| Sitemap restored | 25 |
| Sitemap added | 20 |
| Sitemap removed | 20 |
| Lastmod-only suspected | 5 |

UI 等级：`Critical 90–100`、`High 70–89`、`Medium 40–69`、`Low 0–39`。

### Milestone 4：VPS 友好的轮转调度

Page 新增两个调度字段：

```text
last_detailed_at
needs_detail_check
```

新增、恢复或 lastmod 变化会设置 `needs_detail_check=true`。详细巡检直接在 SQL 中执行：

```sql
ORDER BY needs_detail_check DESC, last_detailed_at ASC, id ASC
LIMIT 100
```

每次尝试后都会更新时间并清除 priority。成功、304 和临时失败都会轮转到队尾，避免失败页面或清单前
100 页永久饿死其余页面。APScheduler 只有一个全局执行线程；多个同时到期的竞品会串行排队。

### Milestone 5：存储与内存保护

- 可见正文默认最多 `100000` 字符，截断后再计算 hash、diff 和写入 SQLite。
- 每页默认保留最近 `5` 个有变化的 Snapshot。
- 内容和 SEO 都没变化时不会创建 Snapshot。
- 详细抓取在 SQL 中完成排序和 LIMIT，不先加载全部 active pages。
- 大型 Sitemap 写入每 `200` 行提交一次，避免长时间占用 SQLite writer lock。

### Milestone 6：最小 UI 升级

- 日志显示 TITLE、H1、DESCRIPTION、CANONICAL、ROBOTS、REDIRECT、CONTENT badges。
- 行内显示重要程度和分数。
- 抽屉先显示发生变化的 SEO 字段 from/to，再显示原有正文 diff；不展示未变化字段。
- 变更日志可按 Critical、High、Medium、Low 筛选。
- 竞品卡片显示近七天高影响变化数。
- “移出 Sitemap”不再使用代表 HTTP 页面删除的措辞或删除线。

### Milestone 7：测试与加固

测试覆盖 Sitemap 生命周期、URL 规范化、SEO 提取、所有字段 diff、HTTP/redirect 变化、正文变化、
无变化、priority 顺序、never-checked 轮转、SQL LIMIT、失败轮转、快照保留、内容长度上限、SQLite
并发设置、分批写入、恶意 XML 和本地端到端抓取。

## 工作原理

```text
APScheduler (1 global worker)
            |
            v
      fetch Sitemap/index
            |
            v
  normalized URL inventory diff
       |             |
       |             +--> Change: added / sitemap_removed / restored / suspected
       v
 priority + oldest detailed-page SELECT ... LIMIT 100
            |
            v
 polite httpx fetch (robots, delay, conditional GET, redirects)
            |
            v
 selectolax SEO + bounded visible text extraction
       |                         |
       v                         v
 Snapshot (max 5/page)    Change(type=modified, score, SEO diff, hunks)
            \___________________________/
                         |
                         v
                  FastAPI + Jinja UI
```

### 基础监控

基础监控始终开启，成本主要是下载 Sitemap XML。首次巡检是静默基线：建立 URL 清单但不为每个初始
URL 写一条 added。第二次开始记录真实差异。Sitemap index、gzip Sitemap 和最多 50,000 个 URL
都受支持。

`<lastmod>` 变化只记录 `suspected`，因为 Sitemap 无法说明页面具体改了什么。没有 lastmod 的页面仍可
检测新增、移出和恢复，但只有详细监控才能识别正文或 SEO 修改。

### 详细监控

详细监控按竞品开启。它复用一个 httpx client，遵守 robots.txt 和 Crawl-delay，向同一 host 的请求默认
至少间隔一秒，并发送 ETag / Last-Modified conditional headers。304 不下载正文，也不创建快照。

403 或 429 会触发 host cooldown。首次收到的响应状态可以进入 Snapshot；cooldown 内后续尝试不会继续
请求目标 host。网络失败不会中止整个竞品巡检，也不会在下一轮持续抢占队头。

## 部署

### 前置条件

- Linux VPS 或本地机器，推荐 2 vCPU / 2 GB RAM。
- Docker Engine 和 Docker Compose v2（`docker compose` 命令）。
- 默认端口 `9527` 可用。
- 用于数据库的持久化目录。

应用没有用户账号、登录、权限系统或 TLS。**不要把 9527 无保护地暴露到公网。** 推荐仅绑定
`127.0.0.1`，再通过带 TLS 和访问控制的反向代理、VPN 或防火墙访问。

### Docker Compose：首次部署

```bash
git clone https://github.com/leon-fong/fuck-competitors.git
cd fuck-competitors

mkdir -p data
docker compose config --services    # 应只输出 app
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 app
curl -fsS http://127.0.0.1:9527/ >/dev/null && echo "app is reachable"
```

打开 `http://SERVER_IP:9527`。如果使用反向代理，建议把 `docker-compose.yml` 的端口改成：

```yaml
ports:
  - "127.0.0.1:9527:9527"
```

Compose 中只有一个 `app` service。Dockerfile 明确使用 `--workers 1`；不要横向启动多个 app 副本，
否则每个副本都有自己的 in-process scheduler，会重复执行巡检。

### 数据持久化

默认挂载：

```yaml
volumes:
  - ./data:/data
```

容器数据库 URL 是 `sqlite:////data/app.db`，主机文件是 `./data/app.db`。`docker compose down`、
`down -v` 和 image rebuild 都不会删除这个 bind-mounted 文件。

如果部署脚本每次 clone 到新目录，请把左侧改成固定绝对路径，例如：

```yaml
volumes:
  - /var/lib/fuck-competitors/data:/data
```

否则“新 clone 目录里的空 `./data`”看起来会像数据丢失。数据库目录必须允许 Docker container 写入。

Compose 还挂载 `./app:/srv/app`，便于直接更新模板和静态文件。生产环境必须保留当前 checkout；若希望
完全使用 image 内代码，可以删除这条 source bind mount，并在每次更新后重新 build。

### Docker 配置覆盖

Docker 默认使用 [app/config.py](app/config.py) 中的值，`FC_DB_URL` 由 Compose 固定到 `/data/app.db`。
要覆盖其他值，在 `docker-compose.yml` 的 `environment` 下取消注释或添加变量：

```yaml
environment:
  - FC_DB_URL=sqlite:////data/app.db
  - FC_DEFAULT_INTERVAL_HOURS=24
  - FC_REQUEST_TIMEOUT=15
  - FC_DETAILED_MAX_PAGES=100
  - FC_SNAPSHOT_RETENTION=5
  - FC_CRAWL_DELAY_SECONDS=1.0
  - FC_MAX_CONTENT_CHARS=100000
```

不要把源码运行所用的 `sqlite:///./data/app.db` 原样覆盖到容器里；容器必须继续使用四个斜杠的
`sqlite:////data/app.db` 才会写入 `/data` mount。

### Makefile 快捷命令

```bash
make up        # build 并后台启动
make logs      # 跟踪日志
make ps        # 查看状态
make restart   # rebuild + recreate
make down      # 停止容器，保留数据库
make build     # 只构建 image
```

Makefile 固定 Compose project name，并关闭 BuildKit，兼容包含中文或其他非 ASCII 字符的项目路径。

### 安全升级

启动时应用会运行 `SQLModel.metadata.create_all()` 和轻量 `_migrate()`，自动增加新列并迁移旧的
`removed` 语义。不使用 Alembic。升级前仍应备份数据库。

最稳妥的停机备份与升级流程：

```bash
docker compose down
cp -a data data.backup-YYYYMMDD-HHMMSS
git pull --ff-only
docker compose up -d --build
docker compose logs --tail=100 app
curl -fsS http://127.0.0.1:9527/ >/dev/null && echo "app is reachable"
```

在线备份可以使用本机 `sqlite3` 的 `.backup`，不要在应用写入时只复制 `app.db` 而忽略 WAL 状态：

```bash
sqlite3 data/app.db ".backup 'app-backup.db'"
```

恢复时先停容器，再把备份恢复为挂载目录中的 `app.db`，然后重新启动。

### 源码运行

```bash
git clone https://github.com/leon-fong/fuck-competitors.git
cd fuck-competitors

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 127.0.0.1 --port 9527 --workers 1
```

源码模式会从当前目录的 `.env` 读取 `FC_` 配置。生产运行不要使用多个 workers；开发时可以使用
`--reload`，但不要让 reload 进程与正式实例同时指向同一个数据库。

## 配置参考

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `FC_DB_URL` | `sqlite:///./data/app.db` | SQLite URL；Docker Compose 会改为 `sqlite:////data/app.db` |
| `FC_DEFAULT_INTERVAL_HOURS` | `24` | 默认巡检间隔 |
| `FC_REQUEST_TIMEOUT` | `15` | 单次 HTTP 请求超时，秒 |
| `FC_MAX_SITEMAP_URLS` | `50000` | 单个竞品一次解析的 URL 上限 |
| `FC_DETAILED_MAX_PAGES` | `100` | 每个竞品每轮详细抓取上限 |
| `FC_SNAPSHOT_RETENTION` | `5` | 每页保留的最近变化快照数 |
| `FC_MAX_CONTENT_CHARS` | `100000` | 每个快照参与存储、hash 和 diff 的正文字符上限 |
| `FC_WRITE_BATCH` | `200` | Sitemap inventory 每 N 行提交一次 |
| `FC_USER_AGENT` | `FuckCompetitors/0.1 …` | Sitemap、robots、页面和 favicon resolver 使用的 User-Agent |
| `FC_RESPECT_ROBOTS` | `true` | 是否遵守 robots.txt |
| `FC_CRAWL_DELAY_SECONDS` | `1.0` | 同一 host 请求的最小间隔；robots Crawl-delay 可提高它 |
| `FC_BLOCK_COOLDOWN_SECONDS` | `900` | 403 或无有效 Retry-After 的 429 后暂停该 host 的秒数 |

详细监控默认值是单个竞品上的开关，不是环境变量；新竞品默认 `detailed_on=false`。

## 数据模型与迁移

SQLite 文件包含四张主表：

| 表 | 关键内容 |
| --- | --- |
| `competitor` | 名称、Sitemap URL、间隔、详细监控开关、状态、上次检查时间 |
| `page` | 原始 URL、active/sitemap_removed、lastmod、HTTP validators、详细轮转字段 |
| `change` | added/sitemap_removed/restored/modified/suspected、时间、JSON detail、已读状态 |
| `snapshot` | SEO 字段、HTTP 状态、最终 URL、bounded content、hash、抓取时间 |

SQLite 连接启用：

```text
WAL journal mode
busy_timeout = 30 seconds
synchronous = NORMAL
check_same_thread = false
```

Sitemap inventory 大批写入会分批 commit；详细抓取每页 commit 一次，避免网络请求期间长期持有 writer
lock。不要让多个 app 实例同时调度并写同一个数据库。

## 验证与测试

安装依赖后，各测试脚本可以直接运行，不要求 pytest：

```bash
python tests/test_basic.py
python tests/test_urlnorm.py
python tests/test_lifecycle.py
python tests/test_detailed.py
python tests/test_queue.py
python tests/test_fetch.py
python tests/test_security.py
python tests/test_concurrency.py
python tests/test_batched_write.py
python tests/e2e_local.py
```

其他发布前检查：

```bash
python -m compileall -q app tests
node --check app/static/app.js           # 若系统安装了 Node.js
docker compose config --services         # 应只输出 app
docker compose config --quiet
```

`tests/e2e_local.py` 只启动本地临时 HTTP server，不依赖外部网站。`tests/seed_demo.py` 会重置它所连接的
数据库并写入演示数据，**不要对生产数据库运行**：

```bash
FC_DB_URL=sqlite:///./data/demo.db python tests/seed_demo.py
```

## 运维与故障排查

### 页面显示正常，但一直没有变化

- 首次抓取是静默基线，本来就不会产生 added 日志。
- 基础监控只能通过 Sitemap 增删和 lastmod 判断；目标不维护 lastmod 时无法发现内容修改。
- 确认该竞品已打开详细监控，才会抓取 SEO 与正文。
- 查看 `docker compose logs app` 是否有 Sitemap URL、robots、DNS 或 timeout 问题。

### 每轮只检查 100 页

这是默认保护，不是卡住。未检查页面会通过 `last_detailed_at` 轮转到后续批次；priority 页面先处理。
可调高 `FC_DETAILED_MAX_PAGES`，但会线性增加请求时间、流量、内存和目标站压力。

### 403、429 或 robots blocked

应用默认遵守 robots.txt。403/429 会触发 cooldown，避免高频重试。优先降低抓取频率或提高 delay；只有在
确认目标 robots 误配置且你有权抓取时才设置 `FC_RESPECT_ROBOTS=false`。

### 数据库锁或重复巡检

- 确认只有一个 Uvicorn worker、一个 container、一个 scheduler 实例。
- 不要同时启动源码版和 Docker 版并让它们写同一个 DB。
- 检查数据库目录可写；SQLite WAL 与 30 秒 busy timeout 会处理正常的短暂竞争。
- 多个同时到期的竞品会在全局 crawl worker 中排队，这是设计行为。

### 重启后像是数据丢失

- 检查当前 checkout 的绝对路径是否变化。
- 检查 Compose 实际 mount：`docker compose config`。
- 检查主机 `./data/app.db` 或固定的 `/var/lib/.../app.db` 是否存在。
- 不要在找回旧数据库前对新的空库持续运行，以免混淆两份数据。

### 端口冲突

把 Compose 左侧 host port 改为其他值，例如 `127.0.0.1:19527:9527`；容器内部仍保持 9527。

## 安全说明

- 没有用户认证、多租户、权限和 TLS；公网部署必须由外部访问控制保护。
- Sitemap XML 使用 `defusedxml`，拒绝 XXE、实体扩展和 billion-laughs 类输入。
- 所有 crawler 请求共享诚实的 User-Agent、robots 检查、per-host delay 和 cooldown。
- 页面正文保存在本机 SQLite；当前版本不会发送给 AI 或第三方分析服务。
- Favicon 最终由访问 UI 的浏览器直接请求目标站，并使用 `no-referrer`。

## 代码结构

```text
app/
├── main.py          # FastAPI lifespan、数据库初始化、scheduler 启动
├── web.py           # Jinja 页面与表单 endpoints
├── service.py       # Sitemap 与详细巡检编排、SQL 轮转选择
├── scheduler.py     # APScheduler 单全局执行线程
├── models.py        # Competitor / Page / Change / Snapshot
├── config.py        # FC_ 环境变量
├── db.py            # SQLite engine、PRAGMA、轻量迁移
├── viewmodels.py    # DB rows -> UI view models
├── monitor/
│   ├── sitemap.py   # Sitemap/index/gzip 抓取与安全解析
│   ├── basic.py     # URL inventory diff
│   ├── urlnorm.py   # 保守 URL 规范化
│   ├── detailed.py  # SEO/正文提取、Snapshot diff、评分和保留
│   ├── diff.py      # 逐行 diff hunks
│   ├── fetch.py     # robots、delay、conditional GET、cooldown
│   └── favicon.py   # favicon resolver
├── templates/       # index.html + drawer/settings partials
└── static/          # vanilla JS、CSS、favicon
```

技术栈：FastAPI、Jinja2、SQLite、SQLModel、APScheduler、httpx、selectolax、defusedxml、vanilla JS、
Docker。没有前端构建步骤。

## 许可证

MIT
