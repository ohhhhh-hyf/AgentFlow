from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from client.config import load_env
from domain.notes.tasks.catalog.store import catalog_meta_path
from tools.ocr.levels.light import LightOcrResult, _safe_stem, run_light_ocr


logger = logging.getLogger(__name__)

META_TOP_KEYS = ("catalog_hints", "knowledge_points")
KNOWLEDGE_TYPES = {"concept", "formula", "theorem", "method", "application", "mixed"}
RANKS = {"1", "2", "3", "4", "5"}
VLM_ROLES = {"ignore", "title", "body", "example", "margin_note", "formula", "emphasis"}
VLM_ROLE_ALIASES = {
    "title_region": "title",
    "background_mark": "emphasis",
    "formula_region": "formula",
    "example_region": "example",
    "note_region": "margin_note",
}

VLM_OBSERVATION_PROMPT = """你是学习笔记视觉观察员。只看版面，不抄全文，不讲解知识。

只输出一个 JSON 对象。第一个字符是 {，最后一个字符是 }。
不要 Markdown 围栏、注释、中文引号、尾随逗号。

只补三类视觉信息：
1. ignore：页眉页脚、印刷厂、页码、装订阴影
2. emphasis：荧光笔、下划线、星号、框起来的关键词；strength 为 1-3
3. 区块角色：title / example / margin_note / formula；title 可带 level 1-3

顶层只能有 reading_order 和 regions。
regions[].role 只能是：ignore, title, example, margin_note, formula, emphasis
不要输出普通正文 body。不要编图片里没有的字。最多 12 条。

合法输出示例：
{"reading_order":["算符","狄拉克符号","算符运算"],"regions":[{"role":"ignore","text":"印刷厂页脚"},{"role":"title","text":"狄拉克符号","level":2},{"role":"emphasis","text":"形式不变性","strength":2},{"role":"formula","text":"F=ma"},{"role":"example","text":"能量本征方程"}]}
"""

META_SYSTEM_PROMPT = """你是 OCR Standard Meta 生成器。只决定目录怎么切，不填满目录的练习/关系/能力标签。

输入：审校 Markdown、OCR 原文、VLM 视觉观察。
输出只能是 JSON object，且只能有 2 个顶层字段：catalog_hints, knowledge_points。

怎么切：
1. 不要用小节标题当该节唯一 KP。同一主题拆 2-6 个可独立学的点。
2. 公式写进 knowledge_items，短式即可。
3. 笔记里没有的不要编。例题、旁注、页眉页脚不要升成章或 KP。
4. catalog_hints 里每一个主题都必须有 KP。名额按主题分配，不要把前面几节写满、后面的节一个点都没有。
5. 若 Markdown 含「第 n 页」注释，把全文当成同一份笔记重切：跨页同名知识点合并为一条，按主题切，不要按页切成多棵树。

VLM 用法：
- ignore：不能当证据
- emphasis：只提高已有点的 importance，不新造点
- reading_order / title：校正主题顺序和层级
- example / margin_note：不要当新章或 KP

字段：
- catalog_hints：title/parent/level(1-3)；单页最多 8 条，多页合并稿最多 24 条
- knowledge_points：每条必须带 topic（所属主题名，不要带「第n页」前缀）。每个主题 2-6 条。字段：title、topic、knowledge_type(concept/formula/theorem/method/application/mixed)、knowledge_items(最多 3 条公式或条件)、importance("1"-"5")、evidence(最多 2 条短证据)

不要输出 review_items、relations、action_items、difficulty、risk_tags、practice_type。
"""


@dataclass(frozen=True)
class StandardOcrResult:
    raw_text: str
    reviewed_markdown: str
    raw_path: Path
    reviewed_path: Path
    meta_path: Path | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    visual: dict[str, Any] = field(default_factory=dict)

    @property
    def files(self) -> list[str]:
        files = [str(self.raw_path), str(self.reviewed_path)]
        if self.meta_path is not None:
            files.append(str(self.meta_path))
        return files


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean_str(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _enum(value: Any, allowed: set[str], default: str = "") -> str:
    text = _clean_str(value)
    return text if text in allowed else default


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _repair_json_text(raw: str) -> str:
    """修 VLM 常见格式问题：围栏、中文引号、尾随逗号、缺逗号、Python 字面量。"""
    text = _strip_json_fence(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    text = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = re.sub(r"}\s*{", "},{", text)
    text = re.sub(r"]\s*\[", "],[", text)
    text = re.sub(r'("(?:\\.|[^"\\])*")\s*"', r'\1, "', text)
    text = re.sub(r'([}\]])\s*"', r'\1, "', text)
    text = re.sub(r"(true|false|null|-?\d+(?:\.\d+)?)\s*\"", r'\1, "', text)
    return text


def _json_from_text(text: str) -> dict[str, Any]:
    candidates = [text or "", _repair_json_text(text or "")]
    last_error: Exception | None = None
    for raw in candidates:
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = exc
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                continue
            try:
                data = json.loads(raw[start : end + 1])
            except json.JSONDecodeError as inner:
                last_error = inner
                continue
        if isinstance(data, list):
            return {"regions": data}
        if isinstance(data, dict):
            return data
    if last_error is not None:
        raise last_error
    return {}


def normalize_visual_observations(
    data: dict[str, Any],
    *,
    max_order: int = 8,
    max_regions: int = 12,
) -> dict[str, Any]:
    reading_order = [
        _clean_str(item) for item in _as_list(data.get("reading_order")) if _clean_str(item)
    ][:max_order]
    regions: list[dict[str, Any]] = []
    raw_regions = data.get("regions")
    if not raw_regions:
        raw_regions = data.get("visual_observations")
    for item in _as_list(raw_regions)[:max_regions]:
        if not isinstance(item, dict):
            continue
        role_raw = _clean_str(item.get("role") or item.get("type"))
        role = _enum(VLM_ROLE_ALIASES.get(role_raw, role_raw), VLM_ROLES)
        text = _clean_str(item.get("text") or item.get("related_text"))
        if not role or not text:
            continue
        if role == "body":
            continue
        row: dict[str, Any] = {"role": role, "text": text}
        if role == "title":
            try:
                level = int(item.get("level") or 0)
            except (TypeError, ValueError):
                level = 0
            if level:
                row["level"] = min(max(level, 1), 3)
        if role == "emphasis":
            try:
                strength = int(item.get("strength") or 0)
            except (TypeError, ValueError):
                strength = 0
            row["strength"] = min(max(strength or 1, 1), 3)
        regions.append(row)
    return {"reading_order": reading_order, "regions": regions}


def _allocate_knowledge_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for item in points:
        topic = _clean_str(item.get("topic")) or "__ungrouped__"
        if topic not in grouped:
            grouped[topic] = []
            order.append(topic)
        if len(grouped[topic]) < 6:
            grouped[topic].append(item)
    out: list[dict[str, Any]] = []
    for topic in order:
        out.extend(grouped[topic])
    return out


def normalize_standard_meta(
    data: dict[str, Any],
    *,
    max_hints: int | None = 8,
) -> dict[str, list[dict[str, Any]]]:
    meta: dict[str, list[dict[str, Any]]] = {key: [] for key in META_TOP_KEYS}

    hint_rows = _as_list(data.get("catalog_hints"))
    if max_hints is not None:
        hint_rows = hint_rows[:max_hints]
    for item in hint_rows:
        if not isinstance(item, dict):
            continue
        title = _clean_str(item.get("title"))
        if not title:
            continue
        try:
            level = int(item.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        meta["catalog_hints"].append(
            {
                "title": title,
                "parent": _clean_str(item.get("parent")),
                "level": min(max(level, 1), 3) if level else "",
            }
        )

    parsed: list[dict[str, Any]] = []
    for item in _as_list(data.get("knowledge_points")):
        if not isinstance(item, dict):
            continue
        title = _clean_str(item.get("title") or item.get("name"))
        if not title:
            continue
        parsed.append(
            {
                "title": title,
                "topic": _clean_str(item.get("topic") or item.get("parent")),
                "knowledge_type": _enum(item.get("knowledge_type"), KNOWLEDGE_TYPES, "mixed"),
                "knowledge_items": [
                    _clean_str(x) for x in _as_list(item.get("knowledge_items")) if _clean_str(x)
                ][:3],
                "importance": _enum(item.get("importance"), RANKS, "3"),
                "evidence": [_clean_str(x) for x in _as_list(item.get("evidence")) if _clean_str(x)][:2],
            }
        )
    meta["knowledge_points"] = _allocate_knowledge_points(parsed)
    return meta


def _visual_observations(image_path: Path, project_root: Path) -> dict[str, Any]:
    try:
        from client import VLMClient

        load_env(project_root / ".env")
        client = VLMClient()
        try:
            raw = client.describe_image(
                image_path,
                VLM_OBSERVATION_PROMPT,
                temperature=0,
                max_tokens=600,
                json_mode=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("VLM json_mode 不可用，回退普通输出：%s", exc)
            raw = client.describe_image(
                image_path,
                VLM_OBSERVATION_PROMPT,
                temperature=0,
                max_tokens=600,
            )
        return normalize_visual_observations(_json_from_text(raw))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Standard OCR VLM 观察失败：%s", exc)
        return {"reading_order": [], "regions": [], "error": str(exc)}


def _generate_meta(
    raw_text: str,
    reviewed_markdown: str,
    visual: dict[str, Any],
    project_root: Path,
    *,
    md_limit: int = 8000,
    raw_limit: int = 3000,
    max_tokens: int = 3000,
    max_hints: int | None = 8,
) -> dict[str, Any]:
    try:
        from tools.ocr.engines import get_llm_client

        load_env(project_root / ".env")
        client = get_llm_client()
        if client is None:
            return normalize_standard_meta({})
        user_prompt = (
            "【审校 Markdown】\n"
            f"{reviewed_markdown[:md_limit]}\n\n"
            "【OCR 原文】\n"
            f"{raw_text[:raw_limit]}\n\n"
            "【VLM】\n"
            f"{json.dumps({k: visual.get(k) for k in ('reading_order', 'regions')}, ensure_ascii=False)}\n\n"
            "只输出 catalog_hints 和 knowledge_points。"
        )
        text = asyncio.run(
            client.text(
                META_SYSTEM_PROMPT,
                user_prompt,
                temperature=0,
                json_mode=True,
                max_tokens=max_tokens,
                label="ocr/standard_meta",
            )
        )
        return normalize_standard_meta(_json_from_text(text), max_hints=max_hints)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Standard OCR meta 生成失败：%s", exc)
        return normalize_standard_meta({})


def _save_meta(meta: dict[str, Any], *, user_id: str, image_path: Path) -> Path:
    path = catalog_meta_path(user_id=user_id, stem=_safe_stem(image_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def combine_page_visuals(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """把各页 VLM 观察收成一份短上下文，供合并稿 meta 使用。"""
    order: list[str] = []
    regions: list[dict[str, Any]] = []
    for idx, page in enumerate(pages, start=1):
        label = f"第{idx}页"
        visual = page.get("visual") if isinstance(page.get("visual"), dict) else {}
        for title in _as_list(visual.get("reading_order")):
            text = _clean_str(title)
            if text:
                order.append(f"{label}/{text}")
        for region in _as_list(visual.get("regions")):
            if not isinstance(region, dict):
                continue
            item = dict(region)
            text = _clean_str(item.get("text"))
            if text:
                item["text"] = f"{label}:{text}"
            regions.append(item)
    return normalize_visual_observations(
        {"reading_order": order, "regions": regions},
        max_order=40,
        max_regions=80,
    )


def save_combined_meta(
    *,
    raw_text: str,
    reviewed_markdown: str,
    pages: list[dict[str, Any]],
    user_id: str,
    output_stem: str,
    project_root: str | Path,
) -> Path:
    """对合并后的 md 再跑一次短 meta，按全书重切，不粘单页 JSON。"""
    visual = combine_page_visuals(pages)
    meta = _generate_meta(
        raw_text,
        reviewed_markdown,
        visual,
        Path(project_root),
        md_limit=24000,
        raw_limit=8000,
        max_tokens=4000,
        max_hints=24,
    )
    return _save_meta(meta, user_id=user_id, image_path=Path(output_stem))


def run_standard_ocr(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    output_stem: str | None = None,
    save_meta: bool = True,
) -> StandardOcrResult:
    root = Path(project_root)
    path = Path(image_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        light_future = pool.submit(
            run_light_ocr,
            path,
            user_id=user_id,
            subject=subject,
            project_root=root,
            output_stem=output_stem,
        )
        visual_future = pool.submit(_visual_observations, path, root)
        light: LightOcrResult = light_future.result()
        visual = visual_future.result()

    meta: dict[str, Any] = {}
    meta_path = None
    if save_meta:
        meta = _generate_meta(light.raw_text, light.reviewed_markdown, visual, root)
        meta_path = _save_meta(
            meta,
            user_id=user_id,
            image_path=Path(output_stem) if output_stem else path,
        )
    return StandardOcrResult(
        raw_text=light.raw_text,
        reviewed_markdown=light.reviewed_markdown,
        raw_path=light.raw_path,
        reviewed_path=light.reviewed_path,
        meta_path=meta_path,
        meta=meta,
        visual=visual,
    )


__all__ = [
    "StandardOcrResult",
    "normalize_standard_meta",
    "normalize_visual_observations",
    "combine_page_visuals",
    "save_combined_meta",
    "run_standard_ocr",
]
