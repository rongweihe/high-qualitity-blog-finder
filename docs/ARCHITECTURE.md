# 中文高质量技术博主发现站：第一版架构规划

日期：2026-04-26

## 1. 产品目标

做一个本地优先、轻量可迭代的网站，用来收集和发现中文高质量技术博主、独立开发者和工程师。第一版重点覆盖：

- AI / LLM / Agent
- 全栈 / 前端 / 后端
- 独立开发 / 产品工程
- 加密货币 / 量化交易 / 套利
- 工程基础设施 / 开源 / 云原生

第一版数据量控制在 500 个以内，优先保证“可验证、可维护、可浏览”，而不是追求一次性收全。

## 2. 高质量定义

默认只展示满足以下条件的博客：

- 中文内容为主。
- 有主站，且主站可访问。
- 最近一年内有文章发布。以当前日期 2026-04-26 计算，最近一年阈值为 `>= 2025-04-26`。
- 能从 Google / 百度 / GitHub / Forever Blog / 站内链接等来源之一追溯到。
- 最好有关联 Twitter/X、GitHub、公众号、即刻、RSS 等外部账号。

实际数据状态分三类：

- `verified`：已确认主站可访问，且最近一年有文章。
- `candidate`：主站存在，但最近文章时间或标签尚未完全确认。
- `hidden`：无法访问、非中文、明显停更或质量不足，默认不展示。

## 3. 推荐技术栈

第一版建议用 Python 本地服务，不引入重型前端框架。

- Web 服务：FastAPI
- 页面渲染：Jinja2 模板
- 交互增强：少量 HTMX 或原生 JS
- 数据库：SQLite
- 数据采集：httpx + BeautifulSoup + feedparser
- 缩略图：优先 OpenGraph 图片；后续可加 Playwright 截图缓存
- 样式：原生 CSS，做 app-shell 布局

这个组合的好处是：本地启动快、调试简单、后续也能平滑迁移到 Postgres 或静态站。

## 4. 系统模块

```text
sources -> collectors -> normalizer -> verifier -> classifier -> SQLite -> FastAPI -> UI
```

### 4.1 sources

初始候选来源：

- GitHub 仓库：`qianguyihao/blog-list`
- Forever Blog：`https://www.foreverblog.cn/blogs.html`
- GitHub 搜索结果：中文 AI / 独立开发 / 全栈 / 量化 / 套利相关仓库和 awesome list
- 站点自带 blogroll / 友情链接
- 博主主页里的 Twitter/X、GitHub、RSS 链接
- 后续手工维护的精选种子列表

### 4.2 collectors

每个来源一个采集器：

- `GithubMarkdownCollector`：抓取 GitHub markdown 列表里的博客链接、标题、描述、分类。
- `ForeverBlogCollector`：解析 Forever Blog 的签约博客列表。
- `BlogrollCollector`：从已验证博客的友情链接中扩展候选。
- `ManualSeedCollector`：读取本地人工整理的 YAML/CSV 种子。

Twitter/X 第一版不建议强依赖爬虫。优先从博主主站、GitHub profile、页面 footer、About 页面中抽取 X 链接；如果后续需要大规模补全，再考虑官方 API 或外部搜索服务。

### 4.3 normalizer

负责把候选链接变成统一结构：

- 统一 URL：去掉 tracking 参数、补全协议、规范化域名。
- 去重：按 canonical URL、根域名、标题近似匹配。
- 提取元信息：站点标题、描述、favicon、OpenGraph 图片、RSS 链接。
- 识别站点类型：个人博客、团队博客、公司内容站、聚合页。

第一版只保留个人博客和独立开发者主页；公司官方博客默认不进入主列表。

### 4.4 verifier

验证核心条件：

- `site_reachable`：HTTP 200 或可接受的重定向。
- `is_chinese`：页面标题、正文、最新文章中文比例较高。
- `has_recent_post`：最近文章时间 `>= 2025-04-26`。
- `has_rss`：能发现 RSS/Atom/feed。
- `has_social_link`：发现 Twitter/X、GitHub、公众号等。

最近文章时间的判断顺序：

1. RSS/Atom 最新 item 的 `published` 或 `updated`
2. `sitemap.xml` 的 `lastmod`
3. 首页 / 归档页 / 文章页里的日期
4. 只能人工确认时标记为 `candidate`

### 4.5 classifier

第一版先用规则分类，后续再加 LLM 辅助。

标签规则示例：

- AI：`AI`、`LLM`、`大模型`、`机器学习`、`深度学习`、`RAG`
- Agent：`Agent`、`智能体`、`MCP`、`workflow`、`function calling`
- 全栈：`React`、`Next.js`、`Vue`、`Node.js`、`全栈`
- 后端：`Go`、`Rust`、`Java`、`Python`、`数据库`、`架构`
- 独立开发：`独立开发`、`indie hacker`、`SaaS`、`产品`
- 加密货币：`crypto`、`Web3`、`区块链`、`交易所`、`链上`
- 交易套利：`量化`、`套利`、`高频`、`交易系统`、`做市`

每个博主可以有多个标签，但主分类只保留 1 到 2 个，避免 UI 过乱。

## 5. 数据模型

核心表建议：

```text
bloggers
- id
- name
- site_url
- canonical_url
- description
- avatar_url
- thumbnail_url
- rss_url
- github_url
- twitter_url
- other_social_urls
- language
- status
- quality_score
- last_post_at
- last_checked_at
- created_at
- updated_at

tags
- id
- slug
- name
- group_name

blogger_tags
- blogger_id
- tag_id

source_refs
- id
- blogger_id
- source_name
- source_url
- raw_title
- raw_description
- collected_at

latest_posts
- id
- blogger_id
- title
- url
- published_at
```

第一版也可以同时导出 `data/bloggers.json`，方便人工修正和未来静态部署。

## 6. 质量评分

用于排序，不直接替代人工判断。

```text
quality_score =
  recent_post_score
  + source_score
  + social_score
  + content_relevance_score
  + site_health_score
```

建议权重：

- 最近一年更新：40
- 来自高质量种子源：20
- 有 RSS / GitHub / Twitter/X：15
- 标签命中 AI / Agent / 全栈 / 独立开发 / 交易套利：15
- 站点访问稳定、标题描述清晰：10

展示默认排序：`quality_score desc, last_post_at desc`。

## 7. UI 规划

第一屏直接是工具，不做营销落地页。

### 7.1 页面结构

- 左侧 sidebar：分类、标签、数量、数据状态筛选。
- 顶部 toolbar：搜索框、排序、只看最近更新、分页尺寸。
- 右侧主区域：博主卡片网格。
- 顶部 tabs：全部、AI、Agent、全栈、后端、独立开发、加密货币、交易套利。

### 7.2 博主卡片

卡片信息：

- 缩略图：优先站点 screenshot，其次 OpenGraph 图片，再其次 favicon/avatar。
- 主站名字。
- 一句话描述。
- 标签 chips。
- 最近更新时间。
- 外链按钮：主站、RSS、GitHub、Twitter/X。
- 来源 badge：GitHub / Forever Blog / Blogroll / Manual。

### 7.3 分页

默认每页 24 个，可选 24 / 48 / 96。URL 参数保持可分享：

```text
/?tag=ai&page=1&page_size=24&sort=quality
```

## 8. 缩略图策略

第一版：

1. 读取 `og:image` 或 `twitter:image`。
2. 没有图片时用 favicon/avatar。
3. 生成统一尺寸卡片封面，避免页面跳动。

第二版：

1. 用 Playwright 打开主站。
2. 截取首屏。
3. 输出 `webp` 到 `/static/thumbs/{blogger_id}.webp`。
4. 定期重刷失败或过期缩略图。

## 9. 数据更新流程

本地命令设计：

```text
python -m app.collect --source github_blog_list
python -m app.collect --source forever_blog
python -m app.verify --recent-since 2025-04-26
python -m app.classify
python -m app.export-json
python -m app.server
```

第一版可以不做复杂后台任务。采集和验证用命令手动跑，网站只读 SQLite。

## 10. 目录结构建议

```text
high-qualitity-blog-finder-site/
  app/
    main.py
    db.py
    models.py
    services/
      search.py
      filters.py
    collectors/
      github_blog_list.py
      forever_blog.py
      blogroll.py
      manual_seed.py
    verifier/
      recency.py
      metadata.py
      social_links.py
    classifier/
      rules.py
    templates/
      base.html
      index.html
      partials/
        blogger_card.html
    static/
      styles.css
      thumbs/
  data/
    seeds.yaml
    bloggers.json
    app.db
  docs/
    ARCHITECTURE.md
  pyproject.toml
  README.md
```

## 11. 第一版里程碑

### M0：规划和骨架

- 确认架构。
- 初始化 FastAPI + SQLite + Jinja2。
- 做空数据页面和基础 UI。

### M1：手工种子可展示

- 建立 `data/seeds.yaml`。
- 录入 30 到 50 个高确定性中文博主。
- 页面支持分类、搜索、分页。

### M2：采集 GitHub blog-list

- 解析 `qianguyihao/blog-list`。
- 导入候选链接。
- 去重、补齐标题和描述。

### M3：采集 Forever Blog

- 解析 Forever Blog 签约博客。
- 过滤非技术/停更/无主站候选。

### M4：验证最近一年更新

- RSS 优先验证。
- sitemap 和 HTML 日期作为补充。
- 标记 `verified` / `candidate` / `hidden`。

### M5：缩略图和美化

- 接入 favicon / OpenGraph 图片。
- 可选加站点截图缓存。
- 完成响应式布局。

## 12. 风险和处理

- 很多中文独立博客没有标准 RSS：保留 `candidate` 状态，允许人工补充。
- Twitter/X 搜索不稳定：第一版只抽取公开链接，不把 X 作为硬性条件。
- Google / 百度验证自动化成本高：先用来源可信度和主站可访问做基础判断，后续做可插拔 search verifier。
- 加密货币套利领域噪声高：标签命中后仍需人工审核，避免把营销站、课程站、交易所软文站放进主列表。
- 500 个以内的上限：按质量分和更新时间截断，低分候选保留在数据库但默认不展示。

## 13. 下一步建议

下一轮可以直接进入 M0 + M1：搭 FastAPI 页面骨架，同时准备 30 到 50 个高确定性的首批博主种子。这样网站能很快有第一版可浏览的东西，再逐步把采集器接上。
