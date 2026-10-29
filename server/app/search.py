"""近似搜索打分（对应 api.md 第 6 节）。

四层加权，取最高分：
1. 完全包含 —— 关键词出现在标题/描述/分类里，优先级最高（matchType=exact）
2. 中文 bigram Dice 系数 —— 解决"错一个字就搜不到"
3. 英文编辑距离（SequenceMatcher）—— 解决 macbok / airpod 这类拼写错误
4. 同义词扩展 —— 单车↔自行车、手机↔iPhone、降噪耳机↔AirPods

字段权重：标题 1.0 / 描述 0.78 / 分类 0.6。
默认阈值 0.34 以下判为不相关（见 GET /items?minScore=）。
"""
import re
from difflib import SequenceMatcher

# 校园闲置高频同义表达。键和值都必须是 _norm 之后的形式（小写、无空格）。
SYNONYMS: dict[str, list[str]] = {
    "手机": ["iphone", "智能机"],
    "苹果手机": ["iphone"],
    "平果手机": ["iphone"],
    "平果": ["iphone", "苹果"],
    "iphone": ["手机", "苹果"],
    "苹果": ["iphone"],
    "macbok": ["macbook"],
    "mac": ["macbook"],
    "笔记本": ["macbook", "电脑"],
    "笔记本电脑": ["macbook", "电脑"],
    "电脑": ["macbook", "笔记本"],
    "平板": ["ipad"],
    "ipad": ["平板"],
    "耳机": ["airpods", "蓝牙耳机"],
    "降噪耳机": ["airpods", "sony"],
    "蓝牙耳机": ["airpods"],
    "单车": ["自行车", "公路车"],
    "自行车": ["单车", "公路车"],
    "公路车": ["公路自行车", "自行车"],
    "计算器": ["卡西欧", "fx991"],
    "台灯": ["护眼灯", "led"],
    "冰箱": ["迷你冰箱"],
    "吹风机": ["电吹风"],
    "书": ["教材", "课本", "图书"],
    "教材": ["书", "课本"],
    "高数": ["高等数学"],
    "考研": ["真题", "考研英语", "考研政治"],
    "外套": ["呢子外套", "大衣"],
    "跑鞋": ["运动鞋"],
    "鞋": ["跑鞋", "运动鞋"],
    "包": ["双肩包", "背包"],
    "哑铃": ["健身", "力量训练"],
    "显示器": ["屏幕", "monitor"],
    "键盘": ["罗技", "logitech"],
    "鼠标": ["罗技", "mouse"],
    "充电宝": ["移动电源"],
    "移动电源": ["充电宝"],
    "固态": ["ssd", "固态硬盘"],
    "硬盘": ["ssd", "固态硬盘"],
    "椅子": ["休闲椅", "座椅"],
    "桌子": ["书桌", "桌"],
}

FIELD_WEIGHTS = {"title": 1.0, "desc": 0.78, "category": 0.6}


def _norm(text: str | None) -> str:
    """小写 + 去掉所有空白，中英文都能直接做子串/二元组匹配。"""
    if not text:
        return ""
    return "".join(ch for ch in text.lower() if not ch.isspace())


def _bigrams(text: str) -> set[str]:
    if not text:
        return set()
    if len(text) < 2:
        return {text}
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _dice(a: str, b: str) -> float:
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 0.0
    return 2 * len(ba & bb) / (len(ba) + len(bb))


def _ascii_similarity(term: str, text: str) -> float:
    """英文/数字片段之间用编辑距离相似度，能吃掉拼写错误。"""
    if not term.isascii():
        return 0.0
    best = 0.0
    for word in re.findall(r"[a-z0-9]+", text):
        best = max(best, SequenceMatcher(None, term, word).ratio())
    return best


def _similarity(term: str, text: str) -> float:
    return max(_dice(term, text), _ascii_similarity(term, text) * 0.95)


def expand_terms(q: str) -> list[str]:
    qn = _norm(q)
    if not qn:
        return []
    terms = [qn]
    for alt in SYNONYMS.get(qn, []):
        alt_n = _norm(alt)
        if alt_n and alt_n not in terms:
            terms.append(alt_n)
    return terms


def score_item(q: str, item: dict) -> tuple[float, str]:
    """返回 (score 0–1, matchType)。"""
    if not q.strip():
        return 1.0, "exact"

    qn = _norm(q)
    terms = expand_terms(q)
    fields = {
        "title": _norm(item.get("title")),
        "desc": _norm(item.get("desc")),
        "category": _norm(item.get("category")),
    }

    best = 0.0
    exact = False

    for term in terms:
        for field, weight in FIELD_WEIGHTS.items():
            text = fields[field]
            if not text:
                continue
            if term in text:
                # 完全包含：字段越短、命中占比越高，分数越接近 1
                coverage = min(1.0, len(term) / max(len(text), 1))
                best = max(best, (0.82 + 0.18 * coverage) * weight)
                if term == qn:
                    exact = True
            else:
                best = max(best, _similarity(term, text) * weight)

    return round(min(best, 1.0), 3), ("exact" if exact else "fuzzy")
