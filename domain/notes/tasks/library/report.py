"""资料入库：多文件写入默认知识库，并给出知识增量与冲突点。"""
from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path
from typing import Any

from tools.knowledge.document_processor import SUPPORTED_EXTS
from tools.knowledge.tool import KnowledgeTool

_FILE_MARK = "【入库文件】"
_CONFLICT_CAP = 8
_UNIT_CAP = 12
_SENT_SPLIT = re.compile(r"(?<=[。！？；!\?\n])")
_STOP = set("的了在是和与及或对把被从到为以会可能进行相关问题情况这个我们没有可以一个")
_PUNCT = set("：:，,。；;！!？?、·()[]【】（）")
_TAIL = set("上占为了是的与和在把被从到以会")
_GENERIC_TOPIC = {
    "答案",
    "解析",
    "函数",
    "课前篇",
    "课前篇自",
    "课堂篇",
    "课标阐释",
    "内容索引",
    "当堂检测",
    "本课结束",
    "微判断",
    "微练习",
    "微思考",
    "探究学习",
    "自主预习",
    "f(x)",
    "奇函数",
    "偶函数",
    "函数答案",
    "函数c",
    "偶函数c",
    "偶函数d",
    "数学抽象",
    "数学运算",
    "逻辑推理",
    "思维脉络",
    "探究一",
    "探究二",
    "探究三",
    "给角求值",
    "给值求值",
    "给值求角",
    "公式解决",
    "式解决给",
    "式推导出",
    "推导出",
    "利用两角",
    "三利用两",
    "素养形成",
    "方法点睛",
    "反思感悟",
    "规范答题",
}
_HEADING_FRAG = (
    "探究",
    "课标",
    "脉络",
    "阐释",
    "给角",
    "给值",
    "素养",
    "当堂",
    "课堂篇",
    "内容索",
    "究一",
    "究二",
    "究三",
    "知识点",
)
_STRUCTURE_BLOBS = (
    "课前篇自主预习课堂篇探究学习内容索引",
    "课标阐释思维脉络",
    "当堂检测本课结束",
    "微判断微练习微思考",
    "反思感悟方法点睛素养形成规范答题",
    "知识点拨名师点析要点笔记",
    "高中同步学案优化设计第一PPT模板网",
    "当堂检测答案",
    "课前篇自主预习",
)


def source_paths_from_context(text: str) -> list[str]:
    raw = text or ""
    if _FILE_MARK not in raw:
        return []
    tail = raw.split(_FILE_MARK, 1)[1]
    paths: list[str] = []
    for line in tail.splitlines():
        item = line.strip().strip('"')
        if not item:
            if paths:
                break
            continue
        if item.startswith("【"):
            break
        paths.append(item)
    return paths


def expand_inputs(raw_paths: list[str | Path]) -> list[Path]:
    files: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"入库路径不存在：{path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTS:
                    files.append(child)
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            raise ValueError(f"不支持的文件格式：{path}")
        files.append(path)
    # 去重并保持顺序
    seen: set[str] = set()
    out: list[Path] = []
    for item in files:
        key = str(item.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lstrip("\ufeff"))


def _units(text: str) -> list[str]:
    parts = [
        item.strip().lstrip("\ufeff")
        for item in _SENT_SPLIT.split(text or "")
        if item.strip()
    ]
    if not parts:
        blob = " ".join((text or "").split()).strip()
        return [blob] if blob else []
    return parts[:_UNIT_CAP]


def _ngrams(text: str, size: int) -> set[str]:
    blob = _compact(text)
    if len(blob) < size:
        return {blob} if blob else set()
    return {blob[i : i + size] for i in range(len(blob) - size + 1)}


def _is_independent(text: str, old_texts: list[str]) -> bool:
    blob = _compact(text)
    if len(blob) < 8:
        return False
    for old in old_texts:
        other = _compact(old)
        if not other:
            continue
        if blob in other or other in blob:
            return False
        grams = _ngrams(blob, 6)
        shared = grams & _ngrams(other, 6)
        if grams and len(shared) / len(grams) >= 0.55:
            return False
    return True


def _topic_score(label: str) -> tuple[int, int, int, int]:
    tail = 1 if label and label[-1] in _TAIL else 0
    digit = 1 if any(ch.isdigit() for ch in label) else 0
    weak = 1 if any(token in (label or "") for token in ("只谈", "本段", "以下", "本题")) else 0
    lead = 1 if label and label[0] in "谈看用把被从对将" else 0
    return (weak, lead, tail, digit, abs(len(label) - 4))


def _topic_label(left: str, right: str) -> str:
    a, b = _compact(left), _compact(right)
    hits: list[str] = []
    limit = min(len(a), len(b), 12)
    for size in range(limit, 3, -1):
        for gram in _ngrams(a, size):
            if gram not in b:
                continue
            if any(ch in _STOP or ch in _PUNCT for ch in gram):
                continue
            hits.append(gram)
    cleaned = []
    for item in hits:
        label = "".join(ch for ch in item if ch not in _PUNCT).strip()
        if len(label) < 4:
            continue
        if any(len(g) >= 3 and (g in label or label in g) for g in _GENERIC_TOPIC):
            continue
        cjk = sum(1 for ch in label if "\u4e00" <= ch <= "\u9fff")
        if cjk < 2:
            continue
        if any(frag in label for frag in _HEADING_FRAG):
            continue
        if any(label in blob for blob in _STRUCTURE_BLOBS):
            continue
        latin = sum(1 for ch in label if ch.isascii() and ch.isalpha())
        if latin >= 2:
            continue
        cleaned.append(label)
    if not cleaned:
        return ""

    def _rank(label: str) -> tuple[int, int, int, int]:
        idx = a.find(label)
        left = a[idx - 1] if idx > 0 else ""
        after_punct = left in _PUNCT or left in "「『（("
        start_pen = 0 if after_punct else (1 if idx == 0 and len(a) > 8 else 0)
        return (*_topic_score(label), start_pen)

    return min(cleaned, key=_rank)


_OUTLINE_HEAD = re.compile(
    r"^(课标阐释|思维脉络|内容索引|探究[一二三123]|课前篇|课堂篇|"
    r"自主预习|探究学习|当堂检测|素养形成|方法点睛)"
)


def _is_chrome(text: str) -> bool:
    blob = _compact(text)
    if blob.startswith("高中同步") or blob.startswith("不可以在以下"):
        return True
    return "PPT模板" in (text or "") or "www." in (text or "").lower()


def _is_outline(text: str) -> bool:
    """课标、探究标题、目录行不是知识主张，不参与冲突。"""
    blob = _compact(text)
    if not blob:
        return True
    if _OUTLINE_HEAD.match(blob):
        return True
    if blob.startswith("探究") and any(
        token in blob for token in ("给角", "给值", "化简", "证明", "条件求值")
    ):
        return True
    return False


def _skip_conflict_unit(text: str) -> bool:
    return _is_chrome(text) or _is_outline(text)


def _ambiguity(left: str, right: str) -> int | None:
    if _skip_conflict_unit(left) or _skip_conflict_unit(right):
        return None
    ja, jb = _ngrams(left, 3), _ngrams(right, 3)
    if not ja or not jb:
        return None
    inter = ja & jb
    union = ja | jb
    jaccard = len(inter) / len(union)
    topic = _topic_label(left, right)
    if not topic:
        return None
    if jaccard > 0.78:
        return None
    if jaccard < 0.20:
        return None
    return max(8, min(92, int(round((1 - jaccard) * 100))))


def _safe_chunks(kb: KnowledgeTool, collection: str = "default") -> list[dict[str, Any]]:
    try:
        return list(kb.list_chunks(collection=collection) or [])
    except Exception:
        return []


def ingest_library(kb: KnowledgeTool, paths: list[Path],
                   collection: str = "default") -> dict[str, Any]:
    before = _safe_chunks(kb, collection)
    old_texts = [str(item.get("text") or "") for item in before]
    files: list[dict[str, str]] = []
    for path in paths:
        stat = kb.add_file(str(path), collection=collection)
        files.append(
            {
                "name": path.name,
                "added": str(stat.get("added") or 0),
                "removed": str(stat.get("removed") or 0),
                "unchanged": str(stat.get("unchanged") or 0),
            }
        )
    incoming_names = {item["name"] for item in files}
    after = _safe_chunks(kb, collection)
    new_chunks = [
        item
        for item in after
        if str((item.get("metadata") or {}).get("source") or "") in incoming_names
    ]
    increment_items: list[dict[str, str]] = []
    by_file: dict[str, int] = {}
    seen_texts = list(old_texts)
    for chunk in new_chunks:
        meta = chunk.get("metadata") or {}
        source = str(meta.get("source") or "")
        for unit in _units(str(chunk.get("text") or "")):
            if _is_chrome(unit):
                continue
            if not _is_independent(unit, seen_texts):
                continue
            seen_texts.append(unit)
            by_file[source] = by_file.get(source, 0) + 1
            excerpt = " ".join(unit.split())
            if len(excerpt) > 80:
                excerpt = excerpt[:79] + "…"
            increment_items.append({"text": excerpt, "source": source})

    conflicts: list[dict[str, Any]] = []
    others = [
        item
        for item in after
        if str((item.get("metadata") or {}).get("source") or "")
    ]
    seen_pairs: set[tuple[str, str, str]] = set()
    for new in new_chunks:
        new_file = str((new.get("metadata") or {}).get("source") or "")
        for new_unit in _units(str(new.get("text") or "")):
            if _skip_conflict_unit(new_unit):
                continue
            for old in others:
                old_file = str((old.get("metadata") or {}).get("source") or "")
                if not new_file or not old_file or new_file == old_file:
                    continue
                for old_unit in _units(str(old.get("text") or "")):
                    if _skip_conflict_unit(old_unit):
                        continue
                    rate = _ambiguity(new_unit, old_unit)
                    if rate is None:
                        continue
                    topic = _topic_label(new_unit, old_unit)
                    key = (topic, *sorted((new_file, old_file)))
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    peer = old_file in incoming_names
                    conflicts.append(
                        {
                            "topic": topic,
                            "new_file": new_file,
                            "old_file": old_file,
                            "ambiguity": str(rate),
                            "peer": "1" if peer else "0",
                            "new_excerpt": " ".join(new_unit.split())[:80],
                            "old_excerpt": " ".join(old_unit.split())[:80],
                        }
                    )
    conflicts.sort(key=lambda item: -int(item["ambiguity"]))
    conflicts = conflicts[:_CONFLICT_CAP]
    return {
        "message": "",
        "increment": str(len(increment_items)),
        "files": files,
        "increment_by_file": [
            {"name": name, "count": str(count)} for name, count in by_file.items()
        ],
        "conflicts": conflicts,
        "items": increment_items[:24],
    }


def _conflict_peer(item: dict[str, Any], batch_names: set[str]) -> bool:
    if str(item.get("peer") or "") == "1":
        return True
    return str(item.get("old_file") or "") in batch_names


def _conflict_sentence(item: dict[str, Any], batch_names: set[str]) -> str:
    topic = item.get("topic") or "同一主题"
    rate = item.get("ambiguity") or "?"
    new_f = item.get("new_file") or "新文件"
    old_f = item.get("old_file") or "库内文件"
    other = "同批上传" if _conflict_peer(item, batch_names) else "库内"
    return (
        f"注意：您上传的《{new_f}》与{other}《{old_f}》"
        f"在「{topic}」上存在 {rate}% 的逻辑歧义，请标注哪份为准。"
    )


def build_library_markdown(draft: dict[str, Any]) -> str:
    increment = int(str(draft.get("increment") or "0") or 0)
    files = [item for item in (draft.get("files") or []) if isinstance(item, dict)]
    by_file = [
        item for item in (draft.get("increment_by_file") or []) if isinstance(item, dict)
    ]
    items = [item for item in (draft.get("items") or []) if isinstance(item, dict)]
    conflicts = [item for item in (draft.get("conflicts") or []) if isinstance(item, dict)]
    batch_names = {str(item.get("name") or "") for item in files if item.get("name")}
    names = "、".join(f"《{item.get('name')}》" for item in files if item.get("name"))
    lines = [
        "# 知识库变化",
        "",
        "这次不是把文件塞进去就结束。下面是这批资料对知识库的**实际改变**。",
        "",
        "## 知识增量",
        "",
        f"**本次新增独立知识点 {increment} 个。**",
        "",
    ]
    if names:
        lines.append(f"来自 {names}。")
        lines.append("")
    if by_file:
        for item in by_file:
            lines.append(f"- 《{item.get('name')}》+{item.get('count')}")
        lines.append("")
    note = str(draft.get("message") or "").strip()
    if note:
        lines.append(note)
        lines.append("")
    if increment == 0 and not note:
        lines.append("库里已经有这些说法，知识边界没有被推开。")
        lines.append("")
    elif items:
        for item in items[:8]:
            src = item.get("source") or ""
            tag = f"（{src}）" if src else ""
            lines.append(f"- {item.get('text') or ''}{tag}")
        lines.append("")
    lines.extend(["## 冲突点", ""])
    if not conflicts:
        lines.append("没有需要你裁决的矛盾。知识库变清楚了，没有变糊涂。")
        lines.append("")
    else:
        lines.append("需要你当一次知识库管理员：同一件事，两份资料说法拧着。")
        lines.append("")
        for i, item in enumerate(conflicts, 1):
            topic = item.get("topic") or "同一主题"
            rate = item.get("ambiguity") or "?"
            new_f = item.get("new_file") or "新文件"
            old_f = item.get("old_file") or "库内文件"
            other = "同批" if _conflict_peer(item, batch_names) else "库内"
            lines.extend(
                [
                    f"### {i}. {topic} · {rate}% 歧义",
                    "",
                    _conflict_sentence(item, batch_names),
                    "",
                    f"- 新上传：《{new_f}》",
                    f"  > {item.get('new_excerpt') or ''}",
                    f"- {other}：《{old_f}》",
                    f"  > {item.get('old_excerpt') or ''}",
                    "",
                    "请标注哪一份为准。",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def build_library_html(draft: dict[str, Any]) -> str:
    increment = int(str(draft.get("increment") or "0") or 0)
    files = [item for item in (draft.get("files") or []) if isinstance(item, dict)]
    items = [item for item in (draft.get("items") or []) if isinstance(item, dict)]
    conflicts = [item for item in (draft.get("conflicts") or []) if isinstance(item, dict)]
    batch_names = {str(item.get("name") or "") for item in files if item.get("name")}
    rows = [
        '<div class="library-report memory-review">',
        '<div class="review-heading">知识库变化'
        '<div class="quiz-hint">看增量，不看进度条</div></div>',
        '<div class="library-hero">',
        '<p class="library-caption">本次新增独立知识点</p>',
        f"<p class=\"library-count\"><strong>{increment}</strong> 个</p>",
        "</div>",
    ]
    if files:
        rows.append('<div class="library-files"><ul>')
        for item in files:
            rows.append(
                "<li>"
                f"《{escape(str(item.get('name') or ''), quote=False)}》"
                f" · 新块 {escape(str(item.get('added') or '0'), quote=False)}"
                "</li>"
            )
        rows.append("</ul></div>")
    if increment and items:
        rows.append('<div class="library-items"><ul>')
        for item in items[:8]:
            src = escape(str(item.get("source") or ""), quote=False)
            text = escape(str(item.get("text") or ""), quote=False)
            tag = f"<span>{src}</span>" if src else ""
            rows.append(f"<li>{text}{tag}</li>")
        rows.append("</ul></div>")
    if conflicts:
        rows.append('<div class="library-conflicts">')
        rows.append("<p>需要你裁决的矛盾：</p>")
        for item in conflicts:
            topic = str(item.get("topic") or "同一主题")
            rate = str(item.get("ambiguity") or "?")
            new_f = str(item.get("new_file") or "新文件")
            old_f = str(item.get("old_file") or "库内文件")
            other = "同批上传" if _conflict_peer(item, batch_names) else "库内"
            rows.append(
                f'<div class="library-verdict" data-topic="{escape(topic)}" '
                f'data-new="{escape(new_f)}" data-old="{escape(old_f)}">'
                f"<p>注意：您上传的《{escape(new_f, quote=False)}》与"
                f"{escape(other, quote=False)}《{escape(old_f, quote=False)}》"
                f"在「{escape(topic, quote=False)}」上存在 "
                f"<strong>{escape(rate, quote=False)}%</strong> 的逻辑歧义。</p>"
                f"<blockquote>新：{escape(str(item.get('new_excerpt') or ''), quote=False)}</blockquote>"
                f"<blockquote>{escape(other, quote=False)}："
                f"{escape(str(item.get('old_excerpt') or ''), quote=False)}</blockquote>"
                '<p class="library-ask">请标注哪一份为准。</p>'
                f'<button type="button" data-pick="new">以《{escape(new_f, quote=False)}》为准</button> '
                f'<button type="button" data-pick="old">以《{escape(old_f, quote=False)}》为准</button>'
                '<p class="library-picked"></p>'
                "</div>"
            )
        rows.append("</div>")
        rows.append(
            "<script>"
            "document.querySelectorAll('.library-verdict button').forEach(function(btn){"
            "btn.addEventListener('click',function(){"
            "var box=btn.closest('.library-verdict');"
            "box.querySelectorAll('button').forEach(function(b){b.classList.remove('is-on');});"
            "btn.classList.add('is-on');"
            "var note=box.querySelector('.library-picked');"
            "if(note){note.textContent=btn.getAttribute('data-pick')==='new'"
            "?'已标注：以新上传为准':'已标注：以对照文件为准';}"
            "});});"
            "</script>"
        )
    else:
        rows.append('<div class="library-peace">没有需要裁决的矛盾。</div>')
    rows.append("</div>")
    return "\n".join(rows)


def attach_library_artifacts(state: dict[str, Any]) -> None:
    """对照页进 rendered；裁决按钮进 library_html。"""
    from tools.domain_engine import line

    sub = line(state, "library")
    draft = dict(sub.get("draft") or {})
    draft["library_html"] = build_library_html(draft)
    sub["rendered"] = build_library_markdown(draft)
    sub["draft"] = draft


def kb_from_env() -> KnowledgeTool:
    fake = os.getenv("KNOWLEDGE_FAKE", "").strip().lower() in {"1", "true", "yes"}
    persist = os.getenv("KNOWLEDGE_PERSIST_DIR") or None
    return KnowledgeTool(fake=fake, persist_dir=persist)
