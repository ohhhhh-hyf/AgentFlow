"""模板 → 会议形态标签（7 类）单点映射。

为什么要这一步（2026-09-18 实测）：调用方选的是**细粒度业务模板**（30 个：产品发布/新闻发布/
课堂记录/就医咨询…），而理解层的 ``scene`` 是**粗粒度形态标签**（7 类），且模型是"读原文自己猜"
——对一场产品发布会，它会填「产品发布」→ 不在 7 类里 → 校验失败白跑一轮（多一次调用 + 12s）；
即使被归一到「通用」，溯源线也拿不到贴合的骨架（``heuristic_scene_label`` 的词表里没有
"发布/宣讲/路演"）。

这里按**模板中文名**（模板首行 ``# 中文名``）把两者接上：程序优先给定形态标签，模型自选的
值只作没有模板时的兜底。映射表是唯一来源，新增模板必须同步登记（守卫会校验覆盖率）。

注意：只暴露**形态标签**，绝不把模板 id/栏目名喂给模型——否则模型会先验地按模板口径写
（发布类就往 brief 里塞卖点/价格），与"只从原文提炼事实"的底线冲突。
"""
from __future__ import annotations

# 模板中文名（= 模板 md 首行 `# 中文名`）→ 7 类形态标签之一
TEMPLATE_SCENE_HINTS: dict[str, str] = {
    # 进展与偏差型（团队例会骨架：进展/偏差/风险/协调）
    "团队例会": "团队例会",
    "项目进度会": "团队例会",
    # 决策评审型（评审对象与范围 / 评审结论 / 行动项）
    "决策评审会": "项目决策与评审",
    "总结复盘会": "项目决策与评审",
    "合同审核": "项目决策与评审",
    # 具体问题型（问题界定 / 整改与时限）
    "新闻发布": "专项讨论会",
    "产品发布": "专项讨论会",
    "招生宣讲": "专项讨论会",
    "就医咨询": "专项讨论会",
    "法律咨询": "专项讨论会",
    "家校沟通": "专项讨论会",
    "沟通交流会": "专项讨论会",
    "政府报告": "专项讨论会",
    "庭审记录": "专项讨论会",
    "心理咨询": "专项讨论会",
    # 讲授研讨型（研讨主题 / 分歧与共识 / 后续）
    "专题讲座": "研讨会",
    "工作研讨会": "研讨会",
    "课堂记录": "研讨会",
    "知识笔记": "研讨会",
    # 想法交锋型（想法汇总 / 取舍）
    "小组讨论": "脑暴/讨论",
    "辩论会": "脑暴/讨论",
    # 受访对话型（关键结论 / 未来计划）
    "采访记录": "采访/对话",
    "调研访谈": "采访/对话",
    "面试报告": "采访/对话",
    "面试复盘": "采访/对话",
    "媒体问答": "采访/对话",
    "对话记录": "采访/对话",
    # 通用兜底
    "通用纪要": "通用",
    "个人备忘": "通用",
    "个人视角纪要": "通用",
    "参观游览": "通用",
}


def _template_name(template_text: str) -> str:
    """取模板中文名：模板首行 ``# 中文名`` 或 ``# [中文名主题]``。"""
    for line in (template_text or "").splitlines():
        s = line.strip()
        if s.startswith("# "):
            title_part = s[2:].strip().strip("[]").strip()
            for k in TEMPLATE_SCENE_HINTS:
                if k == title_part or title_part.startswith(k) or k in title_part:
                    return k
            if not s[2:].strip().startswith("["):
                return s[2:].strip()
        if s:
            break
    return ""


def scene_hint_for_template(template_text: str) -> str:
    """单个模板 → 形态标签；未知/空模板返回空串（由调用方回退到模型自选）。"""
    return TEMPLATE_SCENE_HINTS.get(_template_name(template_text), "")


def scene_hint_for_templates(
    templates: dict[str, str] | None, *, prefer: str = "minutes"
) -> str:
    """本次请求的模板集合 → 形态标签：优先 ``prefer`` 线，否则第一条非空模板。

    多线请求里各线模板可能不同，形态标签取主线的模板并记日志（溯源线自己另有程序判定）。
    """
    if not templates:
        return ""
    if prefer and templates.get(prefer):
        hint = scene_hint_for_template(str(templates[prefer]))
        if hint:
            return hint
    for key in sorted(templates):
        text = str(templates[key] or "")
        if not text.strip():
            continue
        hint = scene_hint_for_template(text)
        if hint:
            return hint
    return ""


__all__ = [
    "TEMPLATE_SCENE_HINTS",
    "scene_hint_for_template",
    "scene_hint_for_templates",
]
