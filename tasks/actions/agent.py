"""actions 待办任务非流式提取 Agent：
调用 LLMClient 提取标准 7 字段待办；
支持纯数据驱动的待办双态执行逻辑（传 time 走 Calendar，未传 time 跳过 Calendar）；
用户级目录物理隔离落盘至 data/{user_id}/output/{request_id}/actions.json。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from infra.calendar import enrich_actions_deadlines
from infra.calendar.llm import CalendarLLM
from infra.llm.client import LLMClient
from tasks.actions.prompts import build_actions_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

STANDARD_ACTION_FIELDS = (
    "title",
    "item",
    "owner",
    "deadline",
    "collaborators",
    "acceptance_criteria",
    "dependency",
)


def _format_aux_item(data: Any) -> str:
    """归一化辅助输入为文本。"""
    if not data:
        return ""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        return "\n".join(f"- {item}" if isinstance(item, str) else str(item) for item in data)
    return str(data).strip()


def build_actions_user_message(transcript: str, texts: dict[str, Any] | None = None) -> str:
    """装配待办提取的 User Message。"""
    parts: list[str] = [f"【会议原文】\n{transcript.strip()}"]
    if texts and isinstance(texts, dict):
        if act_text := _format_aux_item(texts.get("actions_text") or texts.get("candidate_actions")):
            parts.append(f"【用户标记待办原文】\n{act_text}")
        if kp := _format_aux_item(texts.get("keypoints") or texts.get("core_points")):
            parts.append(f"【用户核心关键点】\n{kp}")
        if notes := _format_aux_item(texts.get("notes") or texts.get("user_notes")):
            parts.append(f"【用户划线原话与笔记】\n{notes}")
        if vision := _format_aux_item(texts.get("vision") or texts.get("vision_info") or texts.get("ocr")):
            parts.append(f"【视觉信息参考(OCR)】\n{vision}")
    return "\n\n".join(parts)


def normalize_action_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """标准化单个待办字段，剔除不满足准入门槛（如无责任人）的项。"""
    if not isinstance(raw, dict):
        return None

    item_text = str(raw.get("item") or "").strip()
    owner = raw.get("owner")
    owner_str = str(owner).strip() if owner is not None else ""

    # 准入门槛：责任人和事项正文必须有效
    if not item_text or not owner_str or owner_str.lower() in ("null", "none", "未指定", "待定"):
        return None

    title = str(raw.get("title") or "").strip()
    if not title:
        title = item_text[:12]

    deadline = raw.get("deadline")
    deadline_val = str(deadline).strip() if deadline is not None and str(deadline).strip().lower() not in ("null", "none") else None

    collabs = raw.get("collaborators")
    if isinstance(collabs, list):
        collaborators = [str(c).strip() for c in collabs if str(c).strip()]
    elif isinstance(collabs, str) and collabs.strip():
        collaborators = [collabs.strip()]
    else:
        collaborators = []

    acc = raw.get("acceptance_criteria")
    acceptance_criteria = str(acc).strip() if acc is not None and str(acc).strip().lower() not in ("null", "none") else None

    dep = raw.get("dependency")
    dependency = str(dep).strip() if dep is not None and str(dep).strip().lower() not in ("null", "none") else None

    return {
        "title": title,
        "item": item_text,
        "owner": owner_str,
        "deadline": deadline_val,
        "collaborators": collaborators,
        "acceptance_criteria": acceptance_criteria,
        "dependency": dependency,
    }


async def extract_actions_agent(
    *,
    transcript: str,
    meeting_start_time: str = "",
    texts: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    user_id: str = "default",
    request_id: str = "",
    output_path: Path | str | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """执行待办事项提取，支持基于会议时间的双态执行与用户级目录隔离落盘。

    双态逻辑：
    - 态 A：提供了有效会议时间 (meeting_start_time 或 extra.time 非空)
      -> 必须执行 Calendar 推导，产出并保存 {"actions": [...], "actions_update": [...]}
    - 态 B：未提供会议时间 (为空或未传)
      -> 完全跳过 Calendar (0ms 开销，0 次多余模型调用)，产出并保存 {"actions": [...]}

    Args:
        transcript: 会议原文文本
        meeting_start_time: 会议开始时间（非空触发态 A，空则触发态 B）
        texts: 辅助参考文本字典（actions_text, keypoints, notes, vision）
        extra: 扩展字段字典（可含 time 等）
        user_id: 用户唯一标识，用于目录物理隔离（默认 "default"）
        request_id: 请求跟踪 ID（若为空则自动通过 uuid.uuid4().hex 生成）
        output_path: 输出落盘路径（默认 data/{user_id}/output/{request_id}/actions.json）
        llm_client: 可选的大模型客户端实例

    Returns:
        包含 actions（及 actions_update，若有）、code、message、monitor 等标准字段的响应字典
    """
    start_time = time.perf_counter()
    req_id = request_id or uuid.uuid4().hex
    uid = user_id or "default"
    client = llm_client or LLMClient()
    extra_params = extra or {}

    # 1. 判定双态触发条件：是否提供了有效会议起始时间
    start_time_val = (
        meeting_start_time.strip()
        if meeting_start_time and meeting_start_time.strip()
        else str(extra_params.get("time") or "").strip()
    )
    has_time = bool(start_time_val)

    # 2. 组装输入与 Prompt
    user_message = build_actions_user_message(transcript=transcript, texts=texts)
    system_prompt = build_actions_system_prompt(user_message)

    # 3. 调用 LLMClient 提取初始 7 字段 JSON
    raw_actions_list: list[dict[str, Any]] = []
    try:
        res = await client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_message,
            temperature=0.0,
            max_tokens=4096,
        )
        if isinstance(res, dict):
            raw_actions_list = res.get("actions") or []
        elif isinstance(res, list):
            raw_actions_list = res
    except Exception as exc:
        logger.error(f"[ActionsAgent] LLM 提取待办异常: {exc}", exc_info=True)
        raw_actions_list = []

    # 4. 规范化与准入门槛过滤
    normalized_actions: list[dict[str, Any]] = []
    for item in raw_actions_list:
        norm = normalize_action_item(item)
        if norm is not None:
            normalized_actions.append(norm)

    # 5. 双态分支执行
    payload: dict[str, Any] = {}
    enriched_actions: list[dict[str, Any]] | None = None

    if has_time:
        # 态 A：提供了时间，必须执行 Calendar 绝对时间推导
        try:
            cal_client = CalendarLLM(client)
            enriched_actions = await enrich_actions_deadlines(
                actions=normalized_actions,
                meeting_start_time=start_time_val,
                client=cal_client,
                use_fast_path=True,
            )
        except Exception as cal_err:
            logger.warning(f"[ActionsAgent] Calendar 回填异常: {cal_err}", exc_info=True)
            # 兜底降级
            enriched_actions = []
            for act in normalized_actions:
                item_copy = dict(act)
                item_copy["deadline_raw"] = act.get("deadline")
                item_copy["deadline_display"] = act.get("deadline")
                item_copy["deadline"] = None
                enriched_actions.append(item_copy)

        payload = {
            "actions": normalized_actions,
            "actions_update": enriched_actions,
        }
    else:
        # 态 B：未传时间，完全跳过 Calendar（0ms 开销）
        logger.info("[ACTIONS:STATE] mode=without_time skip_calendar=true")
        payload = {
            "actions": normalized_actions,
        }

    # 6. 用户级隔离落盘：data/{user_id}/output/{request_id}/actions.json
    if output_path:
        target_path = Path(output_path)
    else:
        target_path = DEFAULT_DATA_DIR / uid / "output" / req_id / "actions.json"

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[ARTIFACT:SAVE] type=actions path={target_path}")
    except Exception as io_err:
        logger.warning(f"[ARTIFACT:SAVE:ERROR] type=actions path={target_path} err={io_err}")

    cost_time = round(time.perf_counter() - start_time, 2)
    logger.info(
        f"[ACTIONS:DONE] req_id={req_id} count={len(normalized_actions)} "
        f"calendar={has_time} dur={cost_time:.2f}s file={target_path}"
    )
    response_data: dict[str, Any] = {
        "code": 0,
        "message": "success",
        "request_id": req_id,
        "actions": normalized_actions,
        "monitor": {
            "cost_time": cost_time,
            "total_count": len(normalized_actions),
            "calendar_executed": has_time,
        },
    }
    if has_time and enriched_actions is not None:
        response_data["actions_update"] = enriched_actions

    return response_data
