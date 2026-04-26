# 中文高质量技术博主发现站

本项目第一版是一个本地优先的 FastAPI + SQLite + Jinja2 小网站，用来浏览中文技术博主、独立开发者、AI/Agent、全栈、后端、加密货币与交易套利相关候选博客。

## 启动

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

启动时会自动初始化 `data/app.db`，并从 `data/seeds.yaml` 同步首批手工种子。

## 当前能力

- 左侧分类筛选
- 顶部 tab 筛选
- 关键词搜索
- 分页
- SQLite 数据存储
- Jinja2 服务端渲染
- 手工种子数据源
- GitHub blog-list 采集器
- Forever Blog 采集器
- 最近一年更新验证器

## 数据命令

```bash
python3 -m app.collect --source github_blog_list --max 180
python3 -m app.collect --source forever_blog --max 12 --detail-limit 160
python3 -m app.collect --source blogroll --max 80 --blogroll-depth 1 --blogroll-workers 4
python3 -m app.collect --source blogroll --max 30 --blogroll-depth 1 --blogroll-seed-url https://jiajunhuang.com/
python3 -m app.collect --source all --max 180 --with-blogroll --blogroll-depth 1
python3 -m app.verify --limit 40 --recent-since 2025-04-26
```

## 后续

- 生成站点缩略图缓存
- 给 Forever Blog 和友链采集器加详情页缓存

## 效果图
![效果图](https://img.cdn1.vip/i/69edf3e3a76f7_1777202147.webp)
## 更新
```bash
git remote add origin git@github.com:rongweihe/high-qualitity-blog-finder.git
git branch -M main
git push -u origin main
```
