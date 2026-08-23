from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from tools.memory.store import safe_id

from .medium import MediumOcrResult, SplitPlan, run_medium_ocr


HEAVY_META_SYSTEM_PROMPT = """你是「学习笔记结构化分析器」。你会拿到 OCR 原始文本、审校版 Markdown 和 Medium 版面提示。

任务：生成一个简练有效的 meta.json，用于后续目录生成、复习清单、知识图谱、思维导图和行动清单。

严格原则：
1. llmv2.md 和 OCR 原文是事实来源，不能编造笔记里没有的知识
2. Medium 版面提示只作为阅读顺序、双页结构、背景色重要性加权参考
3. 不确定的公式、符号、上下标不要强行纠正，写入 action_items 作为人工检查项
4. 字段宁可少而稳定，不要为了凑数量扩展类型
5. 输出必须是合法 JSON object，不要 Markdown 代码围栏，不要解释文字

字段要求：只输出以下 5 个顶层字段，不要输出其它字段：
- catalog_hints: 0-12 个，辅助目录层级
- knowledge_points: 0-16 个，核心知识点
- review_items: 0-16 个，可直接用于复习清单
- relations: 0-20 个，用简单关系辅助知识图谱/思维导图
- action_items: 0-8 个，学生接下来要做什么

枚举限制：
- knowledge_points.type 只能是 concept/definition/formula/method/example/mistake
- importance/priority 只能是 high/medium/low
- relations.type 只能是 contains/depends_on/uses/similar_to/contrasts_with/example_of/common_mistake
"""


class HeavyLlmClient(Protocol):
    async def text(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = ...,
        max_tokens: int | None = ...,
        label: str | None = ...,
    ) -> str:
        ...


@dataclass(frozen=True)
class HeavyOcrResult:
    raw_text: str
    reviewed_markdown: str
    raw_path: Path
    reviewed_path: Path
    meta_path: Path
    meta: dict[str, Any]
    split_plan: SplitPlan | None = None
    fallback_reason: str = ""

    @property
    def files(self) -> list[str]:
        return [str(self.raw_path), str(self.reviewed_path), str(self.meta_path)]


def run_heavy_ocr(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    llm_client: HeavyLlmClient | None = None,
) -> HeavyOcrResult:
    """Run Heavy OCR: Medium plus a structured meta.json for catalog/review."""
    medium = run_medium_ocr(
        image_path,
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )
    corrected_markdown = apply_heavy_symbol_corrections(medium.reviewed_markdown)
    if corrected_markdown != medium.reviewed_markdown:
        medium.reviewed_path.write_text(corrected_markdown, encoding="utf-8")
        medium = MediumOcrResult(
            raw_text=medium.raw_text,
            reviewed_markdown=corrected_markdown,
            raw_path=medium.raw_path,
            reviewed_path=medium.reviewed_path,
            split_plan=medium.split_plan,
            fallback_reason=medium.fallback_reason,
        )
    meta, reason = generate_heavy_meta(
        image_path,
        user_id=user_id,
        subject=subject,
        medium_result=medium,
        llm_client=llm_client,
    )
    meta_path = save_heavy_meta(
        image_path,
        meta=meta,
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )
    fallback = "；".join(item for item in (medium.fallback_reason, reason) if item)
    return HeavyOcrResult(
        raw_text=medium.raw_text,
        reviewed_markdown=medium.reviewed_markdown,
        raw_path=medium.raw_path,
        reviewed_path=medium.reviewed_path,
        meta_path=meta_path,
        meta=meta,
        split_plan=medium.split_plan,
        fallback_reason=fallback,
    )


def apply_heavy_symbol_corrections(markdown: str) -> str:
    """Apply conservative math-symbol corrections for high-confidence OCR confusions."""
    text = str(markdown or "")
    if not text:
        return text

    # OCR often reads handwritten phi as "4" when it is used as a function symbol.
    text = re.sub(r"(?<![\w.])4(?=\s*\(\s*[-+]?\s*[xt]\s*\))", "φ", text)
    text = re.sub(r"(?<![\w.])4(?=\s*_\s*[nm]\b)", "φ", text)

    # Handwritten omega is often read as w in hbar/Planck-factor contexts.
    text = re.sub(r"([ħℏ])\s*w\b", r"\1ω", text)
    text = re.sub(r"(?<![A-Za-z])h\s*w(?![A-Za-z])", "hω", text)
    text = re.sub(r"\\hbar\s*w\b", r"\\hbar ω", text)

    # Beta in exponential decay/tunneling terms is often read as Latin B.
    text = re.sub(r"e\^\{\s*-\s*B\s*a\s*\}", r"e^{-βa}", text)
    text = re.sub(r"e\^\{\s*-\s*2\s*B\s*a\s*\}", r"e^{-2βa}", text)
    text = re.sub(r"e\^\s*-\s*B\s*a\b", r"e^{-βa}", text)
    text = re.sub(r"(?<=β)\s*a\b", "a", text)
    return text


def generate_heavy_meta(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    medium_result: MediumOcrResult,
    llm_client: HeavyLlmClient | None = None,
) -> tuple[dict[str, Any], str]:
    base = _empty_meta()
    client = llm_client or _get_llm_client_safe()
    if client is None:
        base["action_items"].append(
            {
                "task": "人工检查 Heavy meta 是否需要补充",
                "reason": "LLM 客户端不可用，当前仅保存空 meta。",
                "priority": "medium",
                "related_topic": "",
            }
        )
        return base, "Heavy meta 生成跳过：LLM 客户端不可用"
    try:
        response = asyncio.run(
            client.text(
                HEAVY_META_SYSTEM_PROMPT,
                _meta_user_prompt(image_path, subject=subject, medium_result=medium_result),
                temperature=0.1,
                max_tokens=7000,
                label="ocr/heavy_meta",
            )
        )
        payload = _json_from_text(str(response))
        return _normalize_meta(payload, base), ""
    except Exception as exc:  # noqa: BLE001
        base["action_items"].append(
            {
                "task": "人工检查 Heavy meta 是否需要补充",
                "reason": f"meta.json 生成失败，当前仅保存空 meta：{type(exc).__name__}: {exc}",
                "priority": "medium",
                "related_topic": "",
            }
        )
        return base, f"Heavy meta 生成失败，已保存最小 meta：{exc}"


def save_heavy_meta(
    image_path: str | Path,
    *,
    meta: dict[str, Any],
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(image_path).stem).strip("._") or "image"
    out_dir = Path(project_root) / "data" / safe_id(user_id) / "knowledge" / "catalogs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe_id(subject)}_{stem}_{stamp}_meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _get_llm_client_safe() -> HeavyLlmClient | None:
    try:
        from tools.ocr.engines import get_llm_client

        return get_llm_client()
    except Exception:  # noqa: BLE001
        return None


def _meta_user_prompt(
    image_path: str | Path,
    *,
    subject: str,
    medium_result: MediumOcrResult,
) -> str:
    plan = _split_plan_payload(medium_result.split_plan)
    return (
        f"图片文件：{Path(image_path).name}\n"
        f"学科：{subject}\n\n"
        "Medium 版面提示 JSON：\n"
        f"{json.dumps(plan, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "OCR 原始文本：\n"
        f"{_clip(medium_result.raw_text, 12000)}\n\n"
        "审校版 Markdown（llmv2.md）：\n"
        f"{_clip(medium_result.reviewed_markdown, 16000)}\n\n"
        "请按系统要求输出 meta.json。"
    )


def _empty_meta() -> dict[str, Any]:
    return {
        "catalog_hints": [],
        "knowledge_points": [],
        "review_items": [],
        "relations": [],
        "action_items": [],
    }


def _split_plan_payload(plan: SplitPlan | None) -> dict[str, Any]:
    if plan is None:
        return {
            "is_double_page": False,
            "confidence": 0.0,
            "reading_order": [],
            "crop_plan": [],
            "visual_hints": {"background_marked_regions": []},
        }
    return {
        "is_double_page": plan.is_double_page,
        "confidence": plan.confidence,
        "reading_order": list(plan.reading_order),
        "crop_plan": [
            {
                "id": region.id,
                "x1_ratio": region.x1_ratio,
                "y1_ratio": region.y1_ratio,
                "x2_ratio": region.x2_ratio,
                "y2_ratio": region.y2_ratio,
            }
            for region in plan.crop_plan
        ],
        "visual_hints": plan.visual_hints,
    }


def _normalize_meta(payload: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    out = _empty_meta()
    for key in ("catalog_hints", "knowledge_points", "review_items", "relations", "action_items"):
        out[key] = _list_of_dicts(payload.get(key))
    if not any(out.values()) and any(base.values()):
        return base
    return out


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _json_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    repaired = _repair_json(raw)
    data = json.loads(repaired)
    if not isinstance(data, dict):
        raise ValueError("Heavy meta 必须是 JSON object")
    return data


def _repair_json(text: str) -> str:
    repaired = str(text or "").strip()
    repaired = repaired.translate(
        str.maketrans({"“": '"', "”": '"', "＂": '"', "‘": "'", "’": "'"})
    )
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    return repaired


def _clip(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...（已截断）"


__all__ = [
    "HEAVY_META_SYSTEM_PROMPT",
    "HeavyOcrResult",
    "generate_heavy_meta",
    "run_heavy_ocr",
    "save_heavy_meta",
]
