#!/usr/bin/env python3
"""
Betty Personal Workbench
Generate news.json from public Google News RSS feeds.

逻辑：
1. 扩大新闻搜索范围，不限制单一行业
2. 每个关键词抓取更多 RSS 结果
3. 优先保留最近 30 天
4. 如果最近 30 天不足，再放宽到最近 90 天
5. 最终最多保留 50 条
6. 按发布时间从新到旧排序
7. 标题去重
8. 保留原始来源和原文链接
"""

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime


# ============================================================
# 1. 新闻搜索关键词
# ============================================================

QUERIES = [
    # 全球供应链 / 物流
    (
        "供应链视角",
        "global supply chain logistics shipping procurement",
        "供应链"
    ),

    # 港口 / 航运 / Freight
    (
        "物流视角",
        "port shipping freight container logistics disruption",
        "物流"
    ),

    # 采购 / 供应商
    (
        "供应商视角",
        "supplier procurement sourcing manufacturing supply chain",
        "供应商"
    ),

    # 汽车 / EV
    (
        "汽车供应链",
        "automotive supply chain EV electric vehicle battery manufacturing",
        "汽车供应链"
    ),

    # 中国供应链
    (
        "中国供应链",
        "China manufacturing supply chain procurement logistics",
        "中国供应链"
    ),

    # 东南亚制造
    (
        "区域供应链",
        "Southeast Asia manufacturing supply chain Thailand Vietnam Indonesia",
        "区域供应链"
    ),

    # 半导体 / 科技
    (
        "科技供应链",
        "semiconductor chip electronics technology supply chain manufacturing",
        "科技供应链"
    ),

    # 能源 / 关键矿产
    (
        "能源与原材料",
        "critical minerals lithium nickel copper battery energy supply chain",
        "原材料"
    ),

    # 贸易 / 关税 / 政策
    (
        "贸易与政策",
        "tariff trade policy import export supply chain regulation",
        "贸易与政策"
    ),

    # 时尚 / 奢侈品 / 零售
    (
        "时尚供应链",
        "fashion luxury retail supply chain sourcing inventory manufacturing",
        "时尚供应链"
    ),
]


# ============================================================
# 2. 参数
# ============================================================

# 优先保留最近多少天（满足则不再放宽）
PRIMARY_DAYS = 30

# 最近 PRIMARY_DAYS 内不足时，放宽到多少天
FALLBACK_DAYS = 90

# 每个RSS查询最多读取多少条
ITEMS_PER_QUERY = 10

# 最终 news.json 最多保存多少条
MAX_ITEMS = 20


# ============================================================
# 3. Google News RSS
# ============================================================

def google_news_rss(query):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en"
    })

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BettyPersonalWorkbench/5.0"
        }
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return ET.fromstring(response.read())


# ============================================================
# 4. XML文字读取
# ============================================================

def text(node, tag):
    element = node.find(tag)

    if element is None:
        return ""

    return (element.text or "").strip()


# ============================================================
# 5. 发布时间解析
# ============================================================

def parse_pub_date(value):
    """
    Google News RSS 通常返回：
    Tue, 19 Aug 2026 10:30:00 GMT
    """

    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


# ============================================================
# 6. 主抓取
# ============================================================

raw_items = []
seen_titles = set()

now = datetime.now(timezone.utc)

primary_cutoff = now - timedelta(days=PRIMARY_DAYS)
fallback_cutoff = now - timedelta(days=FALLBACK_DAYS)


for category, query, stage in QUERIES:

    print(f"\nFetching: {query}")

    try:
        root = google_news_rss(query)

        rss_items = root.findall("./channel/item")[:ITEMS_PER_QUERY]

        for item in rss_items:

            title = text(item, "title")
            link = text(item, "link")
            pub = text(item, "pubDate")
            source = text(item, "source") or "Google News"

            if not title:
                continue

            # ----------------------------------------
            # 去重
            # ----------------------------------------

            normalized_title = " ".join(title.lower().split())

            if normalized_title in seen_titles:
                continue

            seen_titles.add(normalized_title)

            # ----------------------------------------
            # 日期
            # ----------------------------------------

            published_at = parse_pub_date(pub)

            if published_at is None:
                continue

            # ----------------------------------------
            # 保存原始数据
            # ----------------------------------------

            raw_items.append({
                "category": category,
                "date": published_at.astimezone().strftime("%Y-%m-%d"),
                "source": source,
                "title": title,
                "summary": (
                    "公开RSS新闻线索。阅读原文后，在WorkBench里记录："
                    "发生了什么？影响哪个供应链环节？"
                    "下一步应该查看什么数据？"
                ),
                "status": "待核验",
                "stage": stage,
                "url": link,
                "_published": published_at
            })

    except Exception as e:
        print(f"RSS failed: {query}")
        print(e)




# ============================================================
# 7. 按发布时间排序
# ============================================================

raw_items.sort(
    key=lambda x: x["_published"],
    reverse=True
)

# ============================================================
# 8. 时效过滤 + 限量
#    优先保留最近 PRIMARY_DAYS 天；
#    若数量不足，再放宽到 FALLBACK_DAYS 天。
# ============================================================

primary_items = [
    item for item in raw_items
    if (now - item["_published"]).total_seconds() <= PRIMARY_DAYS * 86400
]

if len(primary_items) >= MAX_ITEMS:
    recent_items = primary_items
else:
    recent_items = [
        item for item in raw_items
        if (now - item["_published"]).total_seconds() <= FALLBACK_DAYS * 86400
    ]

final_items = recent_items[:MAX_ITEMS]


# ============================================================
# 9. 删除内部日期字段
# ============================================================

for item in final_items:
    item.pop("_published", None)


# ============================================================
# 10. 如果RSS全部失败，保留一个明确的系统提示
# ============================================================

if not final_items:

    final_items = [
        {
            "category": "系统",
            "date": datetime.now().astimezone().strftime("%Y-%m-%d"),
            "source": "System",
            "title": "今日RSS暂不可用",
            "summary": (
                "自动新闻任务没有成功获取RSS内容。"
                "请检查GitHub Actions运行日志。"
            ),
            "status": "待核验",
            "stage": "系统",
            "url": "https://news.google.com/"
        }
    ]


# ============================================================
# 11. 生成 news.json
# ============================================================

payload = {
    "updatedAt": datetime.now(
        timezone.utc
    ).astimezone().isoformat(
        timespec="minutes"
    ),

    "items": final_items
}


output_path = Path(__file__).resolve().parent / "news.json"

output_path.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


print("\n========================================")
print(f"Wrote {len(final_items)} news items")
print(f"Output: {output_path}")
print("========================================")
