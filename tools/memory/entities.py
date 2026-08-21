"""从原文抽挂钩实体：只靠形态和频次，不维护业务词表。"""
from __future__ import annotations

import re

# 封闭类虚词。只放代词/指示/连词/副词，不放任何业务名词。
_STOP = frozenset(
    """
    我 我们 你 你们 他 他们 她 它
    这 这个 那个 这些 那些 这样 那样
    的 了 着 过 在 是 就 也 还 又 都 很 更 最
    和 与 或 及 以及 或者 并且 而且
    如果 因为 所以 但是 然后 那么 因此 于是
    可以 需要 没有 不是 就是 已经 还是
    什么 怎么 自己 现在 今天 之前 之后
    对于 关于 通过 根据 包括 还有 同时 另外
    一个 一种 一些
    the and for with from that this have been will not
    """.split()
)

# 不能当专名首尾的成分（结构过滤，不是业务黑名单）
_EDGE = set("的了着过在是就也还又都和与或及把被从对把")

_HAN = re.compile(r"[\u4e00-\u9fff]+")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")
# 成对引号。只认开闭同类，避免把半句切成专名。
_QUOTED = re.compile(
    r"「([^」]{2,20})」"
    r"|『([^』]{2,20})』"
    r"|《([^》]{2,20})》"
    r"|“([^”]{2,20})”"
    r"|\"([^\"]{2,20})\""
)
_HAN_CHARS = re.compile(r"[\u4e00-\u9fff]")
_LATIN_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_\- ]{2,23}$")


def extract_quoted(text: str) -> list[str]:
    """按出现序抽出成对引号内的短语（去重）。"""
    out: list[str] = []
    seen: set[str] = set()
    for match in _QUOTED.finditer(text or ""):
        token = next((g for g in match.groups() if g), "")
        token = (token or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def is_key_candidate(token: str) -> bool:
    """短名资格：长度和形态，不看是不是业务词。"""
    token = (token or "").strip()
    if len(token) < 2 or token in _STOP or token.isdigit():
        return False
    if token[0] in _EDGE or token[-1] in _EDGE:
        return False
    han = len(_HAN_CHARS.findall(token))
    if han:
        return 2 <= han <= 12 and len(token) <= 16
    return bool(_LATIN_KEY.fullmatch(token))


def pick_project_key(*texts: str) -> str:
    """从理解文本（及原文）锁定短名。

    只采用引号专名，且必须出现在第一段文本（通常是 purpose）里，
    避免把原文里顺带出现的其它专名锁成项目身份。
    """
    purpose = texts[0] if texts else ""
    if not (purpose or "").strip():
        return ""
    quoted: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for token in extract_quoted(text or ""):
            if token in seen or not is_key_candidate(token):
                continue
            seen.add(token)
            quoted.append(token)
    in_purpose = [token for token in quoted if token in purpose]
    if not in_purpose:
        return ""
    in_purpose.sort(key=lambda token: (purpose.find(token), -len(token)))
    return in_purpose[0]


def extract_entities(text: str, *, limit: int = 20) -> list[str]:
    """从原文抽取可用于匹配的实体，按频次与长度排序。

    只使用：引号内短语、反复出现的 3–4 字中文块、拉丁专名。
    不编造，不用领域词表淘汰「像不像专名」。
    """
    raw = text or ""
    if not raw.strip():
        return []

    scores: dict[str, float] = {}

    def add(token: str, weight: float) -> None:
        token = (token or "").strip()
        if len(token) < 2 or token in _STOP or token.isdigit():
            return
        if token[0] in _EDGE or token[-1] in _EDGE:
            return
        if any(len(s) >= 2 and s in token for s in _STOP):
            return
        scores[token] = scores.get(token, 0.0) + weight

    for quoted in extract_quoted(raw):
        add(quoted, 8.0)

    for lat in _LATIN.findall(raw):
        add(lat, 3.0 if lat[:1].isupper() else 1.5)

    for block in _HAN.findall(raw):
        n = len(block)
        for size in (4, 3):
            if n < size:
                continue
            for i in range(0, n - size + 1):
                add(block[i : i + size], float(size))

    kept = [
        (tok, sc)
        for tok, sc in scores.items()
        if sc >= 6.0 or re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]*", tok)
    ]
    kept.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))

    out: list[str] = []
    for tok, _ in kept:
        if any(tok != other and tok in other for other in out):
            continue
        out.append(tok)
        if len(out) >= limit:
            break
    return out


def overlap_score(query: list[str], stored: list[str]) -> int:
    """查询实体与库存实体的命中数（含合理的互相包含）。"""
    if not query or not stored:
        return 0
    hits = 0
    seen: set[str] = set()
    for q in query:
        if q in seen:
            continue
        for s in stored:
            if q == s or (len(q) >= 3 and len(s) >= 3 and (q in s or s in q)):
                hits += 1
                seen.add(q)
                break
    return hits


# ── 结构化实体（优化 C）：entities 从 list[str] 升级为实体档案 ──
# 实体 = {name, type, first_seen, last_seen, status, sessions[]}
_ENTITY_TYPE_RE = re.compile(r"(项目|工程|系统|平台|厂|公司|集团|中心)")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*")


def entity_type(name: str) -> str:
    """启发式实体类型：项目/组织、技术名、关键词（不维护业务词表）。"""
    text = (name or "").strip()
    if not text:
        return "keyword"
    if _ENTITY_TYPE_RE.search(text):
        return "project"
    if _LATIN_RE.fullmatch(text):
        return "tech"
    return "keyword"


def entity_names(entities: object) -> list[str]:
    """兼容新旧实体格式：dict{name,...} 或 str → name 列表（结构化实体优化后仍可用）。"""
    out: list[str] = []
    for item in entities or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item).strip()
        if name:
            out.append(name)
    return out


def normalize_entities(entities: object, stamp: str = "") -> dict[str, dict[str, Any]]:
    """把新旧格式实体统一成结构化 map：{name: {name, type, first_seen, last_seen, status, sessions[]}}。"""
    out: dict[str, dict[str, Any]] = {}
    for item in entities or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            ent = dict(item)
        else:
            name = str(item).strip()
            ent = {}
        if not name:
            continue
        ent.setdefault("name", name)
        ent.setdefault("type", entity_type(name))
        ent.setdefault("first_seen", stamp)
        ent.setdefault("last_seen", stamp)
        ent.setdefault("status", "active")
        ent.setdefault("sessions", [])
        out[name] = ent
    return out


__all__ = [
    "extract_entities",
    "extract_quoted",
    "is_key_candidate",
    "overlap_score",
    "pick_project_key",
]
