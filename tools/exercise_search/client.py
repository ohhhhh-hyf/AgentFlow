"""题库 HTTP 客户端。纯标准库；成功码实测为 10000。"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import (
    MAX_PAGE_SIZE,
    REQUEST_TIMEOUT,
    SUCCESS_CODE,
    exercise_app,
    exercise_app_secret,
    exercise_bank_base,
    exercise_base,
)
from .match import difficulty_code, parse_difficulty


def _api_get(path: str, *, bank: bool = False) -> Any:
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    raw = f"{ts}-{nonce}-{exercise_app_secret()}"
    sign = hashlib.md5(raw.encode("utf-8")).hexdigest()
    base = exercise_bank_base() if bank else exercise_base()
    req = urllib.request.Request(
        base + path,
        headers={"app": exercise_app(), "ts": ts, "nonce": nonce, "sign": sign},
    )
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if body.get("code") != SUCCESS_CODE:
                raise RuntimeError(
                    f"接口错误 code={body.get('code')} msg={body.get('msg')}"
                )
            return body.get("data")
        except urllib.error.HTTPError as exc:
            last_err = RuntimeError(
                f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:200]}"
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = RuntimeError(f"网络错误: {exc}")
        if attempt == 0:
            time.sleep(1)
    raise last_err or RuntimeError("题库请求失败")


def _to_list(value: Any) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _names(items: Any) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                out.append(name)
        elif str(item).strip():
            out.append(str(item).strip())
    return out


def _field_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("content") or value.get("html") or value.get("text") or ""
    if isinstance(value, list):
        value = "".join(str(item) for item in value if item)
    return str(value or "").strip()


def _options(raw: dict[str, Any]) -> list[str]:
    direct = raw.get("options") or []
    if isinstance(direct, list) and any(str(item).strip() for item in direct):
        return [str(item) for item in direct if str(item).strip()]
    for item in raw.get("accessory") or []:
        if not isinstance(item, dict):
            continue
        opts = item.get("options")
        if isinstance(opts, list) and opts:
            return [str(part) for part in opts if str(part).strip()]
    return []


def parse_question(raw: dict[str, Any], *, truncate: int = 0) -> dict[str, Any]:
    """把 /bank/v1/question 原题收成展示结构。truncate=0 表示题干/解析不截断。"""

    def clip(text: object) -> str:
        value = "" if text is None else str(text)
        if truncate and len(value) > truncate:
            return value[:truncate] + "…(已截断)"
        return value

    answer = raw.get("correct_answer")
    if isinstance(answer, list):
        answer_text = "；".join(str(item) for item in answer if str(item).strip())
    else:
        answer_text = "" if answer is None else str(answer).strip()
    if "<tex" in answer_text.lower() or "\\" in answer_text:
        from .tex import pretty_latex, replace_tex_html

        answer_text = pretty_latex(replace_tex_html(answer_text)) or answer_text
    idea = _field_text(raw.get("idea"))
    step = _field_text(raw.get("step"))
    analysis = _pick_analysis(raw)
    difficulty_value = raw.get("difficulty")
    difficulty_name = str(raw.get("difficulty_str") or "").strip()
    if not difficulty_name and difficulty_value is not None:
        difficulty_name = parse_difficulty(difficulty_value)
    return {
        "id": raw.get("id"),
        "content": clip(raw.get("content")),
        "question_type": str(raw.get("question_type") or "").strip(),
        "type_id": raw.get("type"),
        "difficulty": difficulty_name,
        "difficulty_value": difficulty_value,
        "grade": raw.get("grade"),
        "year": raw.get("year"),
        "region": raw.get("region") or {},
        "analysis": clip(analysis),
        "idea": clip(idea),
        "step": clip(step),
        "keypoints": _names(raw.get("keypoint") or raw.get("keypoints")),
        "sections": _names(raw.get("section") or raw.get("sections")),
        "options": _options(raw),
        "correct_answer": answer_text,
        "source": raw.get("source"),
        "paper": (raw.get("paper_original_name_list") or [None])[0] or "",
    }


def _pick_analysis(raw: dict[str, Any]) -> str:
    """/bank/ 解析在 analysis / idea / step；旧接口偶发 analysis_text。"""
    parts: list[str] = []
    seen: set[str] = set()
    for key in ("analysis", "idea", "step", "summary", "analysis_text"):
        text = _field_text(raw.get(key))
        if not text or text.startswith("经检查") or text == "（暂无文字解析）":
            continue
        if text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return "".join(parts)


def get_courses(subject_id: int | None = None, stage_id: int | None = None) -> list[dict]:
    params: dict[str, Any] = {}
    if subject_id is not None:
        params["subject_id"] = subject_id
    if stage_id is not None:
        params["stage_id"] = stage_id
    path = "/v1/get/course"
    if params:
        path += "?" + urllib.parse.urlencode(params)
    data = _api_get(path)
    return list(data or [])


def get_keypoints(subject_id: int, stage_id: int, name: str | None = None) -> list[dict]:
    params: dict[str, Any] = {"subject_id": subject_id, "stage_id": stage_id}
    if name:
        params["name"] = name
    data = _api_get("/v1/get/key/point?" + urllib.parse.urlencode(params), bank=True)
    return list(data or [])


def get_question_types(subject_id: int, stage_id: int) -> list[dict]:
    params = {"subject_id": subject_id, "stage_id": stage_id}
    data = _api_get("/v1/get/question/type?" + urllib.parse.urlencode(params), bank=True)
    flat: list[dict] = []

    def walk(nodes: Any) -> None:
        for node in nodes or []:
            payload = (node or {}).get("data") or {}
            if payload.get("id") is not None:
                flat.append(
                    {
                        "id": payload.get("id"),
                        "name": payload.get("name"),
                        "parent_id": payload.get("parent_id"),
                    }
                )
            walk((node or {}).get("children"))

    walk(data)
    return flat


def get_textbook_versions(
    course_id: int | None = None,
    subject_id: int | None = None,
    stage_id: int | None = None,
    name: str | None = None,
) -> list[dict]:
    params: dict[str, Any] = {}
    if course_id is not None:
        params["course_id"] = course_id
    if subject_id is not None:
        params["subject_id"] = subject_id
    if stage_id is not None:
        params["stage_id"] = stage_id
    if name:
        params["name"] = name
    path = "/v1/get/textbook-version"
    if params:
        path += "?" + urllib.parse.urlencode(params)
    data = _api_get(path) or {}
    if isinstance(data, dict):
        return list(data.get("version_list") or [])
    return list(data or [])


def get_textbooks(
    version_id: int | None = None,
    textbook_id: str | None = None,
    grade_id: int | None = None,
) -> list[dict]:
    params: dict[str, Any] = {}
    if version_id is not None:
        params["version_id"] = version_id
    if textbook_id:
        params["textbook_id"] = textbook_id
    if grade_id is not None:
        params["grade_id"] = grade_id
    path = "/v1/xkwtextbook" if version_id is not None else "/v1/get/textbook"
    if params:
        path += "?" + urllib.parse.urlencode(params)
    data = (_api_get(path, bank=version_id is not None) if version_id is not None else _api_get(path)) or {}
    if isinstance(data, dict):
        return list(data.get("textbook_list") or [])
    return list(data or [])


def get_questions(
    course_id: int,
    *,
    page: int = 1,
    page_size: int = 10,
    keyword: str | None = None,
    difficulty: str | int | None = None,
    qtype: Any = None,
    section: Any = None,
    keypoint: Any = None,
    grade: Any = None,
    book_id: int | None = None,
    year: str | None = None,
    order: int | None = None,
    truncate: int = 0,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "course_id": course_id,
        "page": page,
        "page_size": min(int(page_size), MAX_PAGE_SIZE),
    }
    for key, value in (
        ("type", qtype),
        ("section", section),
        ("keypoint", keypoint),
        ("grade", grade),
    ):
        items = _to_list(value)
        if items:
            params[key] = items
    code = difficulty if isinstance(difficulty, int) else difficulty_code(difficulty)
    for key, value in {
        "keyword": keyword,
        "difficulty": code,
        "book_id": book_id,
        "year": year,
        "order": order,
    }.items():
        if value is not None and value != "":
            params[key] = value
    data = _api_get("/v1/question?" + urllib.parse.urlencode(params, doseq=True), bank=True)
    if isinstance(data, dict):
        rows = data.get("list") or []
    else:
        rows = data or []
    return [
        parse_question(item, truncate=truncate)
        for item in rows
        if isinstance(item, dict)
    ]


__all__ = [
    "get_courses",
    "get_keypoints",
    "get_question_types",
    "get_questions",
    "get_textbook_versions",
    "get_textbooks",
    "parse_question",
    "_pick_analysis",
]
