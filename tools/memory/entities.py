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


# ── 业务泛词：跨会议高频、无项目区分度的实体候选 ──
# 绑定计分与强命中资格不认这些词（精确整词匹配；
# 「蒙泽厂区」「小艺慧记Agent」这类含专名的实体不受影响）。
_GENERIC_ENTITY_STOP = frozenset(
    """
    项目 项目组 会议 例会 周会 月会 年会 大会
    验收 汇报 总结 复盘 评审 检查 审核 评估 审查
    沟通 讨论 研讨 交流 对接 协调 推进 跟进 落实
    工作 计划 任务 安排 进度 需求 问题 风险 阻塞 变更
    方案 措施 目标 结果 结论 决定 决议 事项 议题 内容
    团队 小组 成员 领导 负责人 甲方 乙方 客户 用户
    公司 部门 单位 现场 工程 施工 设计 报告 资料 文档
    测试 上线 发布 交付 实施 运维 开发 产品 运营
    本周 上周 下周 本月 上月 下月 今年 去年 明年
    上午 下午 今天 昨天 明天 阶段 月度 季度 年度 每周 每月
    """.split())


def is_generic_entity(token: str) -> bool:
    """业务泛词判定（精确整词）：绑定计分与强命中资格不认。"""
    return (token or "").strip() in _GENERIC_ENTITY_STOP


_SPEAKER_RE = re.compile(r"^([^\n：:]{1,16})[：:]", re.M)
_SPEAKER_PAREN_RE = re.compile(r"[（(][^）)]*[)）]")


def speaker_names(transcript: str) -> set[str]:
    """对话行首的发言人名（「周宁：」「林夏（算法）：」式）。

    发言人名同团队跨会议共享，作为实体无项目区分度，
    绑定计分与注入复核时应剔除。括号内的角色标注会被剥掉。
    """
    out: set[str] = set()
    for match in _SPEAKER_RE.finditer(transcript or ""):
        raw = match.group(1).strip()
        if not raw:
            continue
        base = _SPEAKER_PAREN_RE.sub("", raw).strip()
        for cand in (raw, base):
            if cand and len(cand) >= 2:
                out.add(cand)
    return out


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


def entity_names(entities: object) -> list[str]:
    """兼容新旧实体格式：dict{name,...} 或 str → name 列表。"""
    out: list[str] = []
    for item in entities or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item).strip()
        if name:
            out.append(name)
    return out


__all__ = [
    "entity_names",
    "extract_entities",
    "extract_quoted",
]
