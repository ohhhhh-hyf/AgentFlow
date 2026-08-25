# -*- coding: utf-8 -*-
"""意图识别 Agent —— LLM prompt 与输出契约。"""
from __future__ import annotations

from .schema import TASK_SPECS


def _task_lines() -> list[str]:
    lines: list[str] = []
    for task, spec in sorted(TASK_SPECS.items()):
        req = "、".join(spec.get("required") or []) or "无"
        opt = "、".join(spec.get("optional") or []) or "无"
        lines.append(f"- {task}（domain={spec['domain']}）：必需[{req}] 可选[{opt}] — {spec['desc']}")
    return lines


INTENT_SYSTEM_PROMPT = """你是「意图识别 Agent」。用户会用一句话表达想做的事，你要：
1. 识别出要执行的任务（可多个，按先后顺序排进 plan）
2. 从句子中抽取每个任务的参数（文件路径、用户ID、学科等）
3. 判断任务间依赖：后一个任务需要前一个任务产出时，在 needs 里写上前置任务的 task 名
4. 完全确定不了的参数用 null（字符串字段用 ""），不要编造文件路径

支持的任务：
{tasks}

判断规则：
- 一句含多个任务时按用户说的先后顺序排（"先 OCR 识别再入库"→ ocr 在前、library 在后，library.needs=["ocr"]）
- 有确定性产出依赖的任务必须写 needs（如 入库→目录→复习；OCR→入库；纪要→行动项）
- 参数里的文件/图片路径要原样照抄用户给的字符串；没给路径的任务该参数留空
- "数学/语文/物理"等学科词 → subject；"用户1/我/张三"等 → user_id（抽不到留空，由调用方上下文补）

示例：
用户："先ocr识别图片再入库，最后出数学的复习清单"
输出：plan=[{"task":"ocr","params":{"input":["图片路径"]},"needs":[],"note":"识别图片"},
            {"task":"library","params":{"file":["识别出的md"],"user_id":"","subject":"数学"},"needs":["ocr"],"note":"入库"},
            {"task":"checklist","params":{"user_id":"","subject":"数学"},"needs":["library"],"note":"复习清单"}]
"""


def build_intent_user_prompt(text: str, context: str = "") -> str:
    parts = ["用户这句话：", text]
    if context.strip():
        parts.append("")
        parts.append("已知上下文（可作默认参数，用户句子里的值优先）：")
        parts.append(context)
    parts.append("")
    parts.append("输出：")
    return "\n".join(parts)


INTENT_OUTPUT_CONTRACT = """{
  "plan": [
    {
      "task": "任务名（必须是上面列出的任务）",
      "params": {"参数名": 值, "file": ["路径1", "路径2"]},
      "needs": ["依赖的前置任务名"],
      "note": "这个任务在做什么（一句话）"
    }
  ],
  "explanation": "给用户看的整体解释（一句话）"
}"""


__all__ = ["INTENT_SYSTEM_PROMPT", "INTENT_OUTPUT_CONTRACT", "build_intent_user_prompt"]
