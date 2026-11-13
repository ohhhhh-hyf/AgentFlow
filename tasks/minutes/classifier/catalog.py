"""智能模板场景候选集与分类 Prompt (零旧代码依赖).

核心能力:
1. 维护全量 29 个普通场景 与 20 个议题专属场景;
2. 依据模式 (agenda / normal) 严格隔离候选集;
3. 组装极简分类 System Prompt 与 User Message.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SceneEntry:
    """单个场景定义."""

    id: str
    name: str
    category: str
    description: str
    has_agenda: bool


SCENE_CATALOG: tuple[SceneEntry, ...] = (
    # 会议类 (全部支持议程)
    SceneEntry("team_meeting", "团队例会", "会议", "固定周期召开，成员逐人汇报近期工作与进展；以人头为主线，而不是围绕单一项目展开。", True),
    SceneEntry("project_progress", "项目进度会", "会议", "围绕同一个项目的里程碑、排期、问题与风险同步进展；多人协作，以项目为主线而非逐人周报。", True),
    SceneEntry("decision_review", "决策评审会", "会议", "对重大方案或资源分配进行评审：有人汇报方案，评委质询讨论，最终形成有约束力的决策或结论。", True),
    SceneEntry("workshop_session", "工作研讨会", "会议", "针对具体业务痛点或技术难题，跨部门集思广益，产出解决方案或改进方向；不一定形成正式拍板。", True),
    SceneEntry("retrospective_session", "总结复盘会", "会议", "项目或阶段结束后复盘：对照目标与实际结果，分析偏差原因，沉淀经验并制定改进措施。", True),
    SceneEntry("exchange_forum", "沟通交流会", "会议", "形式灵活的信息交流、宣讲或介绍，重在传递信息与建立沟通；通常没有评审、答辩或正式拍板。", True),

    # 学习类
    SceneEntry("class_transcript", "课堂记录", "学习", "大中小学课堂教学：教师系统讲授核心知识点，伴随师生提问、互动、练习与课后复习需求。", True),
    SceneEntry("special_lecture", "专题讲座", "学习", "专家就某一前沿或特定主题做系统性讲解（讲座/演讲），以一对多讲授为主，知识密度高、用于拓宽认知。", True),
    SceneEntry("group_seminar", "小组讨论", "学习", "围绕具体知识或话题的自由讨论：多视角交流、深化理解，属于学习场景；不产出业务方案或正式决策。", True),
    SceneEntry("knowledge_memo", "知识笔记", "学习", "碎片化知识的结构化整理与提炼，便于长期检索；常见于内容推荐、好物分享、评测对比等泛指知识。", True),
    SceneEntry("debate_forum", "辩论会", "学习", "正反方围绕同一议题立论、驳论、自由辩论，有明确立场、攻防与胜负/评判。", False),

    # 访谈类
    SceneEntry("research_dialogue", "调研访谈", "访谈", "带有研究目的与假设的访谈：按提纲或标准化问题提问，挖掘受访者真实需求、行为动机与市场机会。", True),
    SceneEntry("interview_transcript", "采访记录", "访谈", "以人物故事、个性化观点和细节为主的采访，为新闻报道或人物刻画提供第一手素材。", True),

    # 面试类
    SceneEntry("hiring_report", "面试报告", "面试", "面试官视角：围绕候选人的专业能力、综合素质与文化匹配度进行评估，形成结构化招聘结论。", False),
    SceneEntry("interview_debrief", "面试复盘", "面试", "候选人视角：复盘自己在面试中的表现、回答得失、暴露的问题与后续改进点。", False),

    # 医疗类
    SceneEntry("clinical_advisory", "就医咨询", "医疗", "围绕患者生理症状、既往病史与检查结果展开的医学咨询，目标是形成诊断结论与治疗建议。", False),
    SceneEntry("psychological_session", "心理咨询", "医疗", "在保密环境中围绕情绪困扰、心理机制与行为模式展开的咨询，提供情感支持与心理干预。", False),

    # 法律类
    SceneEntry("legal_advisory", "法律咨询", "法律", "针对具体法律纠纷或合规疑问，由专业人士给出法律意见、风险提示与应对策略。", True),
    SceneEntry("court_transcript", "庭审记录", "法律", "法庭审理过程的客观记录：法庭调查、举证质证、双方辩论、最后陈述与裁判结果。", False),
    SceneEntry("contract_vetting", "合同审核", "法律", "逐条审查合同或协议条款的合法性与严密性，识别履约风险、责任漏洞与修改建议。", False),

    # 新闻/发布类
    SceneEntry("media_briefing", "新闻发布", "新闻", "企业或机构面向媒体的正式信息发布：以通稿式陈述为主，集中传递重大事件、企业动态或官方立场。", True),
    SceneEntry("product_launch", "产品发布", "新闻", "商业或技术产品的发布：介绍核心卖点、技术突破、市场定位、发售信息与用户价值。", False),
    SceneEntry("government_bulletin", "政府报告", "新闻", "政府工作报告或官方通报：系统汇报施政成果、政策举措与未来规划，回应公共关切。", True),
    SceneEntry("media_qa_session", "媒体问答", "新闻", "以记者或公众提问、官方回应为主的问答环节：围绕质疑、热点或敏感事项进行澄清与表态。", True),

    # 日常/其他类
    SceneEntry("personal_memo", "个人备忘", "日常", "个人随手记录：灵感、待办、生活琐事或片段信息，形式简短；不是多人对话或正式会议。", False),
    SceneEntry("conversation_transcript", "对话记录", "日常", "日常人际对话记录：多轮往来，保留关键信息、情绪与关系脉络，非正式、无固定议程。", True),
    SceneEntry("site_visit_tour", "参观游览", "日常", "参观或游览过程的记录：按时间或空间线索串联所见所闻、讲解信息与主观感受。", True),
    SceneEntry("home_school_liaison", "家校沟通", "日常", "家长与学校之间的沟通：同步学生在校表现、成长动态、问题与协同教育安排。", True),
    SceneEntry("general_minutes", "通用纪要/其他", "日常", "不属于以上场景，或无法可靠判断时选择。", True),
)

SCENE_BY_ID: dict[str, SceneEntry] = {entry.id: entry for entry in SCENE_CATALOG}

NORMAL_CANDIDATE_IDS: tuple[str, ...] = tuple(entry.id for entry in SCENE_CATALOG)  # 29 个
AGENDA_CANDIDATE_IDS: tuple[str, ...] = tuple(
    entry.id for entry in SCENE_CATALOG if entry.has_agenda
)  # 20 个


def candidate_ids_for_mode(has_agenda: bool = False) -> tuple[str, ...]:
    """按模式返回候选集：议程模式 20 个，普通模式 29 个."""
    return AGENDA_CANDIDATE_IDS if has_agenda else NORMAL_CANDIDATE_IDS


def build_candidate_block(candidate_ids: Iterable[str]) -> str:
    """生成候选场景列表文本."""
    wanted = set(candidate_ids)
    return "\n".join(
        f"- {entry.id}（{entry.name}）：{entry.description}"
        for entry in SCENE_CATALOG
        if entry.id in wanted
    )


CLASSIFIER_SYSTEM_PROMPT = """# Role
你是会议场景分类器。你只判断一段会议文本最匹配哪个模板场景，不写纪要，不解释判断过程。

# Task
阅读【待检测文本】，从【候选场景】中选出唯一最匹配的英文模板 ID，并给出 confidence。

判断顺序：
1. 参与角色：谁在说——团队成员、主讲人、面试官、医生、律师、媒体、家长等；
2. 会议目的：进度同步、方案评审、决策拍板、授课、访谈、咨询、发布、复盘等；
3. 流程结构：逐人汇报、方案评审、讲授、问答、访谈、庭审、参观等；
4. 结论形态：是否形成明确决议、是否有交付承诺、是否只是信息交流。

如果文本明显属于【候选场景】之外的专业场景，或无法可靠判断，选择 general_minutes。
不要为了凑一个专用场景而硬选相近模板。

# 候选场景
{{CANDIDATE_SCENES}}

# Output Format
只输出标准 JSON，不要解释，不要 markdown 围栏：
{"template": "project_progress", "confidence": 0.86}

规则：
- template 必须是【候选场景】中的英文模板 ID；
- confidence 必须是 0~1 的小数；
- 无法判断时 template 填 general_minutes；
- 除了这个 JSON 对象，严禁输出任何其他内容。
"""


def build_classifier_system_prompt(has_agenda: bool = False) -> str:
    """组装分类器 System Prompt (自动根据是否有议程注入 20 或 29 个场景)."""
    candidates = candidate_ids_for_mode(has_agenda=has_agenda)
    block = build_candidate_block(candidates)
    return CLASSIFIER_SYSTEM_PROMPT.replace("{{CANDIDATE_SCENES}}", block)


def build_classifier_user_message(transcript_sample: str, agenda_text: str = "") -> str:
    """组装待检测 User Message."""
    parts: list[str] = []
    if agenda := (agenda_text or "").strip():
        parts.append("【现场审定的有效议题清单】\n" + agenda)
    parts.append("【待检测文本】\n" + (transcript_sample or "").strip())
    return "\n\n".join(parts)
