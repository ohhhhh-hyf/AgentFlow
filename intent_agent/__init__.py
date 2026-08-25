# -*- coding: utf-8 -*-
"""意图识别 Agent —— 统一入口。

用法（终端）：
    python -m intent_agent.cli "把ocr_file里的图片识别后入库到数学"
    python -m intent_agent.cli "帮我出数学的复习清单" --user_id 1

编程调用：
    from intent_agent import parse
    plan = parse("先OCR识别再入库", ctx_params={"user_id": "1", "subject": "数学"})
    plan.to_dict()  # {"explanation", "plan": [...], "execution": [[...]]}
"""
from .resolve import Plan, TaskPlan, build_plan, parse
from .schema import DEPENDS, TASK_SPECS, known_tasks

__all__ = ["Plan", "TaskPlan", "build_plan", "parse", "TASK_SPECS", "DEPENDS", "known_tasks"]
