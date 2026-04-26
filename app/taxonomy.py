from __future__ import annotations

from typing import Dict, Iterable, List, Set


DEFAULT_TAGS = [
    {"slug": "ai", "name": "AI", "group": "topic", "order": 10},
    {"slug": "agent", "name": "Agent", "group": "topic", "order": 11},
    {"slug": "fullstack", "name": "全栈", "group": "topic", "order": 20},
    {"slug": "frontend", "name": "前端", "group": "topic", "order": 21},
    {"slug": "backend", "name": "后端", "group": "topic", "order": 22},
    {"slug": "indie", "name": "独立开发", "group": "topic", "order": 30},
    {"slug": "product", "name": "产品", "group": "topic", "order": 31},
    {"slug": "crypto", "name": "加密货币", "group": "topic", "order": 40},
    {"slug": "trading", "name": "交易套利", "group": "topic", "order": 41},
    {"slug": "infra", "name": "工程基础设施", "group": "topic", "order": 50},
    {"slug": "opensource", "name": "开源", "group": "topic", "order": 51},
    {"slug": "python", "name": "Python", "group": "language", "order": 60},
    {"slug": "go", "name": "Go", "group": "language", "order": 61},
    {"slug": "rust", "name": "Rust", "group": "language", "order": 62},
    {"slug": "java", "name": "Java", "group": "language", "order": 63},
    {"slug": "css", "name": "CSS", "group": "frontend", "order": 70},
    {"slug": "swift", "name": "Swift", "group": "language", "order": 71},
    {"slug": "newsletter", "name": "周刊", "group": "format", "order": 80},
    {"slug": "personal", "name": "个人博客", "group": "format", "order": 81},
    {"slug": "foreverblog", "name": "十年之约", "group": "source", "order": 90},
    {"slug": "github-list", "name": "GitHub 榜单", "group": "source", "order": 91},
    {"slug": "blogroll", "name": "友链发现", "group": "source", "order": 92},
]


KEYWORDS: Dict[str, Iterable[str]] = {
    "ai": ["ai", "人工智能", "机器学习", "深度学习", "大模型", "llm", "nlp", "rag", "神经网络", "模型"],
    "agent": ["agent", "智能体", "mcp", "function calling", "workflow", "claude code", "copilot", "cursor"],
    "fullstack": ["全栈", "fullstack", "full-stack", "web 应用", "web开发", "node", "next.js", "django", "flask"],
    "frontend": ["前端", "frontend", "javascript", "typescript", "react", "vue", "css", "浏览器", "vite", "webpack"],
    "backend": ["后端", "backend", "服务端", "server", "数据库", "分布式", "微服务", "架构", "rpc", "api"],
    "indie": ["独立开发", "indie", "个人产品", "side project", "自由职业", "小产品", "产品化"],
    "product": ["产品", "设计", "增长", "saas", "创业", "商业化", "用户体验"],
    "crypto": ["区块链", "web3", "crypto", "ethereum", "以太坊", "solana", "比特币", "链上", "defi"],
    "trading": ["量化", "套利", "交易", "做市", "高频", "投资", "金融", "trading", "精算", "风控"],
    "infra": ["kubernetes", "k8s", "云原生", "容器", "sre", "devops", "linux", "网络", "基础设施", "运维"],
    "opensource": ["开源", "open source", "github", "贡献者", "维护者", "作者"],
    "python": ["python", "django", "flask", "pytorch"],
    "go": ["golang", "go语言", " go ", "go、", "go，"],
    "rust": ["rust"],
    "java": ["java", "spring", "jvm"],
    "css": ["css"],
    "swift": ["swift", "ios"],
    "newsletter": ["周刊", "newsletter"],
}


TECH_CORE_TAGS = {
    "ai",
    "agent",
    "fullstack",
    "frontend",
    "backend",
    "indie",
    "product",
    "crypto",
    "trading",
    "infra",
    "opensource",
    "python",
    "go",
    "rust",
    "java",
    "css",
    "swift",
}


def classify_tags(text: str, extra_tags: Iterable[str] = ()) -> List[str]:
    haystack = f" {text.lower()} "
    tags: Set[str] = set(extra_tags)
    for slug, keywords in KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            tags.add(slug)
    tags.add("personal")
    return sorted(tags, key=_tag_order)


def is_tech_relevant(tags: Iterable[str]) -> bool:
    return bool(TECH_CORE_TAGS.intersection(tags))


def _tag_order(slug: str) -> int:
    for tag in DEFAULT_TAGS:
        if tag["slug"] == slug:
            return int(tag["order"])
    return 999
