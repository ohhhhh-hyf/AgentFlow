from __future__ import annotations

import os
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from client import VLMClient
from client.config import load_env
from tools.memory.store import safe_id
from tools.ocr import _clean_ocr_text
from tools.ocr.adapter import recognize_image
from tools.ocr.reconstruct import reconstruct_markdown, review_markdown

from .light import LightOcrResult, run_light_ocr, save_light_ocr_outputs


MEDIUM_LAYOUT_PROMPT = """你是笔记图片的版面规划器。

你只做版面提示，不要识别全文，不要整理笔记内容，不要判断旋转。

如果不是左右双页，返回 is_double_page=false。
如果是左右双页，返回左右页裁剪方案。裁剪比例使用 0 到 1 的相对坐标。
中缝附近可以保留少量重叠，避免切掉文字。

严格输出一个 JSON object：
- 第一个字符必须是 {
- 最后一个字符必须是 }
- 不要解释文字
- 不要 Markdown 代码围栏
- 不要尾随逗号
- 字符串必须使用英文双引号
- 布尔值必须使用 true/false

JSON schema 示例：
{
  "is_double_page": true,
  "confidence": 0.86,
  "split_strategy": "vertical_gutter",
  "split_ratio": 0.50,
  "reading_order": ["left", "right"],
  "crop_plan": [
    {"id": "left", "x1_ratio": 0.0, "y1_ratio": 0.0, "x2_ratio": 0.515, "y2_ratio": 1.0},
    {"id": "right", "x1_ratio": 0.485, "y1_ratio": 0.0, "x2_ratio": 1.0, "y2_ratio": 1.0}
  ],
  "notes": []
}"""
MEDIUM_SPLIT_PROMPT = MEDIUM_LAYOUT_PROMPT

MIN_DOUBLE_PAGE_CONFIDENCE = 0.65
GUTTER_OVERLAP_RATIO = 0.015


class MediumVlmClient(Protocol):
    def describe_image(
        self,
        image_path: str | Path,
        prompt: str = ...,
        *,
        temperature: float | None = ...,
        max_tokens: int | None = ...,
        extra_body: dict[str, Any] | None = ...,
    ) -> str:
        ...


@dataclass(frozen=True)
class CropRegion:
    id: str
    x1_ratio: float
    y1_ratio: float
    x2_ratio: float
    y2_ratio: float


@dataclass(frozen=True)
class SplitPlan:
    is_double_page: bool
    confidence: float
    reading_order: tuple[str, ...]
    crop_plan: tuple[CropRegion, ...]
    visual_hints: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class MediumOcrResult:
    raw_text: str
    reviewed_markdown: str
    raw_path: Path
    reviewed_path: Path
    split_plan: SplitPlan | None = None
    fallback_reason: str = ""
    debug_files: tuple[Path, ...] = ()

    @property
    def files(self) -> list[str]:
        return [str(self.raw_path), str(self.reviewed_path), *[str(path) for path in self.debug_files]]


def run_medium_ocr(
    image_path: str | Path,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
    vlm_client: MediumVlmClient | None = None,
    min_confidence: float = MIN_DOUBLE_PAGE_CONFIDENCE,
) -> MediumOcrResult:
    """Run Medium OCR: Light plus VLM-guided double-page split."""
    path = Path(image_path)
    if not path.is_file():
        raise ValueError(f"图片不存在：{path}")

    try:
        plan = plan_double_page_split(path, project_root=project_root, vlm_client=vlm_client)
    except Exception as exc:  # noqa: BLE001
        light = run_light_ocr(
            path,
            user_id=user_id,
            subject=subject,
            project_root=project_root,
        )
        return _from_light(light, fallback_reason=f"VLM 双页规划失败，已回退 Light：{exc}")

    if not _is_usable_double_page_plan(plan, min_confidence=min_confidence):
        light = run_light_ocr(
            path,
            user_id=user_id,
            subject=subject,
            project_root=project_root,
        )
        reason = "VLM 判断不是可靠双页，已回退 Light"
        return _from_light(light, split_plan=plan, fallback_reason=reason)

    try:
        raw_text, reviewed_markdown, debug_files = _recognize_double_page(
            path,
            plan,
            user_id=user_id,
            subject=subject,
            project_root=project_root,
        )
    except Exception as exc:  # noqa: BLE001
        light = run_light_ocr(
            path,
            user_id=user_id,
            subject=subject,
            project_root=project_root,
        )
        return _from_light(light, split_plan=plan, fallback_reason=f"分页 OCR 失败，已回退 Light：{exc}")

    saved = save_light_ocr_outputs(
        path,
        raw_text=raw_text,
        reviewed_markdown=reviewed_markdown,
        user_id=user_id,
        subject=subject,
        project_root=project_root,
    )
    return MediumOcrResult(
        raw_text=saved.raw_text,
        reviewed_markdown=saved.reviewed_markdown,
        raw_path=saved.raw_path,
        reviewed_path=saved.reviewed_path,
        split_plan=plan,
        debug_files=tuple(debug_files),
    )


def plan_double_page_split(
    image_path: str | Path,
    *,
    project_root: str | Path,
    vlm_client: MediumVlmClient | None = None,
) -> SplitPlan:
    load_env(Path(project_root) / ".env")
    client = vlm_client or VLMClient()
    errors: list[str] = []
    for _attempt in range(2):
        response = client.describe_image(
            image_path,
            prompt=MEDIUM_LAYOUT_PROMPT,
            temperature=0.0,
            max_tokens=1800,
        )
        try:
            return parse_split_plan(response)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
    raise ValueError("VLM layout_plan 解析失败：" + "；".join(errors))


def parse_split_plan(text: str) -> SplitPlan:
    payload = _json_from_text(text)
    is_double = bool(payload.get("is_double_page"))
    confidence = _clamp_float(payload.get("confidence"), 0.0, 1.0)
    reading_order = tuple(
        _normalize_region_id(str(item).strip())
        for item in (payload.get("reading_order") or ["left", "right"])
        if str(item).strip()
    )
    crop_plan = tuple(_parse_crop_region(item) for item in (payload.get("crop_plan") or []) if isinstance(item, dict))
    if is_double and len(crop_plan) < 2:
        crop_plan = _default_crop_plan(payload.get("split_ratio"))
    return SplitPlan(
        is_double_page=is_double,
        confidence=confidence,
        reading_order=reading_order or ("left", "right"),
        crop_plan=crop_plan,
        visual_hints=_normalize_visual_hints(payload.get("visual_hints")),
        raw=payload,
    )


def _recognize_double_page(
    image_path: Path,
    plan: SplitPlan,
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> tuple[str, str, list[Path]]:
    ordered_regions = _ordered_regions(plan)
    debug_files: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="agentflow_medium_ocr_") as temp_dir:
        crop_paths = _crop_regions(image_path, ordered_regions, Path(temp_dir))
        debug_files = _save_debug_crops(
            image_path,
            ordered_regions,
            crop_paths,
            user_id=user_id,
            subject=subject,
            project_root=project_root,
        )
        page_blocks: list[str] = []
        all_lines: list[dict] = []
        for idx, (region, crop_path) in enumerate(zip(ordered_regions, crop_paths), start=1):
            raw_payload = recognize_image(str(crop_path))
            page_text = _raw_payload_to_text(raw_payload)
            if page_text:
                page_blocks.append(page_text)
            lines = list(raw_payload.get("lines") or [])
            all_lines.extend(_tag_page_lines(lines, idx, region.id))

    raw_text = "\n\n".join(block for block in page_blocks if block.strip()).strip()
    if not raw_text:
        raw_text = "（服务器 OCR 未识别到文字）"
    if not all_lines:
        empty = "（OCR 未识别到文字）"
        return raw_text, empty, debug_files

    draft = reconstruct_markdown(all_lines)
    reviewed, _review_notes = review_markdown(draft, all_lines)
    return raw_text, reviewed, debug_files


def _is_usable_double_page_plan(plan: SplitPlan, *, min_confidence: float) -> bool:
    return (
        plan.is_double_page
        and plan.confidence >= min_confidence
        and len(plan.crop_plan) >= 2
        and set(plan.reading_order).intersection({region.id for region in plan.crop_plan})
    )


def _ordered_regions(plan: SplitPlan) -> list[CropRegion]:
    by_id = {region.id: region for region in plan.crop_plan}
    ordered = [by_id[item] for item in plan.reading_order if item in by_id]
    ordered.extend(region for region in plan.crop_plan if region.id not in {item.id for item in ordered})
    return ordered[:2]


def _crop_regions(image_path: Path, regions: list[CropRegion], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    with Image.open(image_path) as image:
        width, height = image.size
        for region in regions:
            left = int(round(region.x1_ratio * width))
            top = int(round(region.y1_ratio * height))
            right = int(round(region.x2_ratio * width))
            bottom = int(round(region.y2_ratio * height))
            left = max(0, min(left, width - 1))
            top = max(0, min(top, height - 1))
            right = max(left + 1, min(right, width))
            bottom = max(top + 1, min(bottom, height))
            crop = image.crop((left, top, right, bottom))
            out = output_dir / f"{_safe_id(region.id)}.jpg"
            crop.convert("RGB").save(out, format="JPEG", quality=95)
            result.append(out)
    return result


def _save_debug_crops(
    image_path: Path,
    regions: list[CropRegion],
    crop_paths: list[Path],
    *,
    user_id: str,
    subject: str,
    project_root: str | Path,
) -> list[Path]:
    if not _debug_crops_enabled():
        return []
    stamp = datetime_now()
    out_dir = (
        Path(project_root)
        / "data"
        / safe_id(user_id)
        / "ocr"
        / safe_id(subject)
        / "debug"
        / f"{_safe_id(image_path.stem)}_{stamp}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for index, (region, crop_path) in enumerate(zip(regions, crop_paths), start=1):
        target = out_dir / f"{index:02d}_{_safe_id(region.id)}.jpg"
        with Image.open(crop_path) as image:
            image.convert("RGB").save(target, format="JPEG", quality=95)
        saved.append(target)
    plan_path = out_dir / "split_plan.json"
    plan_path.write_text(
        json.dumps(
            [
                {
                    "id": region.id,
                    "x1_ratio": region.x1_ratio,
                    "y1_ratio": region.y1_ratio,
                    "x2_ratio": region.x2_ratio,
                    "y2_ratio": region.y2_ratio,
                }
                for region in regions
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return saved


def _debug_crops_enabled() -> bool:
    value = os.getenv("OCR_SAVE_SPLIT_DEBUG", "true")
    return value.strip().lower() not in {"0", "false", "no", "off", "关"}


def datetime_now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _parse_crop_region(item: dict[str, Any]) -> CropRegion:
    region_id = str(item.get("id") or item.get("name") or "").strip() or "page"
    x1 = _clamp_float(item.get("x1_ratio"), 0.0, 1.0)
    y1 = _clamp_float(item.get("y1_ratio"), 0.0, 1.0)
    x2 = _clamp_float(item.get("x2_ratio"), 0.0, 1.0)
    y2 = _clamp_float(item.get("y2_ratio"), 0.0, 1.0)
    if x2 <= x1:
        x2 = min(1.0, x1 + 0.5)
    if y2 <= y1:
        y2 = min(1.0, y1 + 1.0)
    return CropRegion(
        id=_normalize_region_id(region_id),
        x1_ratio=x1,
        y1_ratio=y1,
        x2_ratio=x2,
        y2_ratio=y2,
    )


def _default_crop_plan(split_ratio: Any = None) -> tuple[CropRegion, CropRegion]:
    try:
        split = float(split_ratio)
    except (TypeError, ValueError):
        split = 0.5
    split = max(0.35, min(0.65, split))
    return (
        CropRegion("left", 0.0, 0.0, min(1.0, split + GUTTER_OVERLAP_RATIO), 1.0),
        CropRegion("right", max(0.0, split - GUTTER_OVERLAP_RATIO), 0.0, 1.0, 1.0),
    )


def _raw_payload_to_text(payload: dict[str, Any]) -> str:
    lines = [
        _clean_ocr_text(item.get("text"))
        for item in (payload.get("lines") or [])
        if isinstance(item, dict) and _clean_ocr_text(item.get("text"))
    ]
    return "\n".join(lines).strip()


def _tag_page_lines(lines: list[dict], page_index: int, region_id: str) -> list[dict]:
    tagged: list[dict] = []
    for item in lines:
        row = dict(item)
        row["page_index"] = page_index
        row["page_region"] = region_id
        tagged.append(row)
    return tagged


def _normalize_visual_hints(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"background_marked_regions": []}
    return {
        "background_marked_regions": [
            _normalize_hint_item(item)
            for item in (value.get("background_marked_regions") or [])
            if isinstance(item, dict)
        ],
    }


def _normalize_hint_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ("location", "notes"):
        if item.get(key) not in (None, ""):
            normalized[key] = str(item.get(key)).strip()
    normalized["confidence"] = _clamp_float(item.get("confidence"), 0.0, 1.0)
    return normalized


def _from_light(
    result: LightOcrResult,
    *,
    split_plan: SplitPlan | None = None,
    fallback_reason: str = "",
) -> MediumOcrResult:
    return MediumOcrResult(
        raw_text=result.raw_text,
        reviewed_markdown=result.reviewed_markdown,
        raw_path=result.raw_path,
        reviewed_path=result.reviewed_path,
        split_plan=split_plan,
        fallback_reason=fallback_reason,
        debug_files=(),
    )


def _json_from_text(text: str) -> dict[str, Any]:
    raw = _extract_json_candidate(text)
    candidates = [raw, _repair_json_candidate(raw)]
    last_error: Exception | None = None
    data: Any = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError as exc:
            last_error = exc
    else:
        if last_error is not None:
            raise last_error
        raise ValueError("VLM split plan 为空")
    if not isinstance(data, dict):
        raise ValueError("VLM split plan 必须是 JSON object")
    return data


def _extract_json_candidate(text: str) -> str:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return raw
    return raw[start : end + 1].strip()


def _repair_json_candidate(text: str) -> str:
    repaired = str(text or "").strip()
    translations = str.maketrans(
        {
            "“": '"',
            "”": '"',
            "„": '"',
            "‟": '"',
            "＂": '"',
            "‘": "'",
            "’": "'",
        }
    )
    repaired = repaired.translate(translations)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    return repaired


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _normalize_region_id(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"左", "左页", "left_page", "page_left"}:
        return "left"
    if lowered in {"右", "右页", "right_page", "page_right"}:
        return "right"
    return _safe_id(lowered or value)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "page"


__all__ = [
    "CropRegion",
    "MEDIUM_SPLIT_PROMPT",
    "MediumOcrResult",
    "SplitPlan",
    "parse_split_plan",
    "plan_double_page_split",
    "run_medium_ocr",
]
