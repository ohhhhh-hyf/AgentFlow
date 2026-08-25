# -*- coding: utf-8 -*-
"""意图识别 Agent —— LLM prompt 与输出契约。"""
from __future__ import annotations

from .schema import TASK_KEYWORDS, TASK_SPECS


def _task_lines() -> list[str]:
    lines: list[str] = []
    for task, spec in sorted(TASK_SPECS.items()):
        req = "、".join(spec.get("required") or []) or "无"
        opt = "、".join(spec.get("optional") or []) or "无"
        kws = "、".join(TASK_KEYWORDS.get(task, ())[:3]) or "—"
        lines.append(
            f"- {task}（用户常用说法：{kws}；domain={spec['domain']}）："
            f"必需[{req}] 可选[{opt}] — {spec['desc']}"
        )
    return lines


INTENT_SYSTEM_PROMPT = """你是「意图识别与任务规划 Agent」。用户会用一句话表达想做的事或提问，你要：
1. 识别出要执行的操作任务（可多个，按先后顺序排进 plan）；若用户只是单纯问答（如概念解释/问事实/打招呼），输出空 plan=[] 并在 explanation 说明
2. 从句子中准确抽取每个任务的参数（文件路径、用户ID、学科、项目等）
3. 精确判断任务间依赖：后一个任务依赖前一个任务产出时，在 needs 里写上前置任务的 task 名；无相互依赖的任务可并行执行
4. 完全确定不了的参数用 null（字符串字段用 ""），不要虚构文件路径

支持的任务：
{tasks}

判断规则：
- 复习/备考类（"快考试了帮我整理复习计划"、"期末划重点"）→ 规划目录与清单两阶段：[catalog, checklist]
- 会议分析类（"总结会议要点并提取待办和导图"）→ [minutes_generation, action_items, mindmap]（后三者均依赖 minutes_generation，但后三者之间可并行）
- 资料建库类（"把图片识别后存入数学知识库"）→ [ocr, library]（library.needs=["ocr"]）
- 单纯知识问答/闲聊（"牛顿第二定律是什么"、"你好"、"什么是向量数据库"）→ plan=[]，explanation="此问题适合直接对话问答"
- 参数提取："数学/物理/化学"等 → subject；"用户1/张三" → user_id；"晨会/项目A" → project

示例 1：
用户："快考试了，帮我整理一份物理复习计划"
输出：plan=[{"task":"catalog","params":{"subject":"物理"},"needs":[],"note":"构建核心知识大纲"},
            {"task":"checklist","params":{"subject":"物理"},"needs":["catalog"],"note":"生成考点复习清单"}]

示例 2：
用户："总结会议纪要，顺便把待办事项、风险点和思维导图一起导出来"
输出：plan=[{"task":"minutes_generation","params":{},"needs":[],"note":"生成会议纪要"},
            {"task":"action_items","params":{},"needs":["minutes_generation"],"note":"提取待办事项"},
            {"task":"risk","params":{},"needs":["minutes_generation"],"note":"分析潜在风险"},
            {"task":"mindmap","params":{},"needs":["minutes_generation"],"note":"生成思维导图"}]
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
