# 拆分自原大文件，保留：test_agenda_template_resolution…

from core.execution.hard_execution import is_agenda_enhanced_mode
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.meeting_core.prompts import (
    MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
)
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from domains.meeting.agenda_engine import (
    ValidAgendaItem,
    AgendaProcessResult,
    process_agenda_for_minutes,
    probe_valid_agendas,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import DiscussionBlock
from domains.meeting.orchestrator import _Nodes
from app.tasks import _prepare
from app.schemas import TaskRequest
from tests.support.fakes import make_minutes_mock_client as _make_minutes_mock_client, run_minutes_graph as _run_minutes_graph

pytestmark = pytest.mark.integration

_EN_AGENDA = """
| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
| --- | --- | --- | --- |
| 01 | Architecture Review | Alice Chen | 20 min |
| 02 | Release Plan | Bob Lee | 15 min |
"""

_EN_TRANSCRIPT = (
    "[00:00:05] Carol Wu: Good morning everyone. Let's get started.\n\n"
    "[00:00:15] Carol Wu: Next up, Alice Chen.\n\n"
    "[00:00:25] Alice Chen: The architecture review covers the gateway redesign. "
    "We measured 120 ms latency and will release the new version next month.\n\n"
    "[00:10:00] Carol Wu: Moving on to the next item, Bob.\n\n"
    "[00:10:10] Bob Lee: The release plan has three milestones. "
    "We will complete testing by November and launch in December.\n\n"
    "[00:20:00] Carol Wu: That's all for today. Thanks everyone.\n"
)

_ZH_AGENDA = """
| 序号 | 议题名称 | 汇报人/主讲人 |
| --- | --- | --- |
| 01 | 架构评审 | 张三 |
| 02 | 发布计划 | 李四 |
"""

_ZH_TRANSCRIPT = (
    "张三 00:01\n关于架构评审，网关重构把时延降低到120ms，下月发布新版本。\n\n"
    "李四 00:10\n关于发布计划，我们有三个里程碑，十一月完成测试，十二月上线。\n"
)



def test_agenda_template_resolution():
    from app.config import resolve_template_format, resolve_agenda_template_format

    # 1. 议题模式下加载通用纪要：命中 resources/agenda_templates/zh/general_minutes.md
    agenda_fmt = resolve_agenda_template_format("general_minutes")
    from core.templates.router._gate import scan_fixed_bracket_literals
    assert scan_fixed_bracket_literals(agenda_fmt) == [], "agenda template must not have unparsed fixed bracket literals"
    assert "以现场审定的有效议题清单为主线展开" in agenda_fmt
    assert "每个议题以「### 一. 议题名称」顶格列出" in agenda_fmt
    assert "**业务子主题**" in agenda_fmt
    assert "#### 1. 子主题名称" not in agenda_fmt
    assert "采用议题聚类" not in agenda_fmt

    # 2. 常规模式下加载通用纪要：原模板 resources/templates/general_minutes.md 保持不变
    legacy_fmt = resolve_template_format("general_minutes")
    assert "采用议题聚类" in legacy_fmt
    assert "以现场审定的有效议题清单为主线展开" not in legacy_fmt

    # 3. 议题模式下加载已定制的 project_progress：命中 resources/agenda_templates/zh/project_progress.md
    agenda_proj_fmt = resolve_agenda_template_format("project_progress")
    assert "以现场审定的有效议题清单为主线展开，每个议题下独立设立一张明细表格" in agenda_proj_fmt

    # 4. 议题模式下加载已定制的 decision_review：命中 resources/agenda_templates/zh/decision_review.md
    agenda_dec_fmt = resolve_agenda_template_format("decision_review")
    assert "以现场审定的有效评审议题为主线展开，每个议题下独立设立一张论证明细表格" in agenda_dec_fmt

    # 5. 议题模式下加载已定制的 workshop_session：命中 resources/agenda_templates/zh/workshop_session.md
    agenda_ws_fmt = resolve_agenda_template_format("workshop_session")
    assert "以现场审定的有效议题清单为主线展开" in agenda_ws_fmt
    assert "多方向探讨或观点交锋以独立加粗行「**业务子主题/探讨方向**」划分段落" in agenda_ws_fmt

    # 6. 议题模式下加载已定制的 retrospective_session：命中 resources/agenda_templates/zh/retrospective_session.md
    agenda_retro_fmt = resolve_agenda_template_format("retrospective_session")
    assert scan_fixed_bracket_literals(agenda_retro_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_retro_fmt
    assert "每条以反映具体交付物或量化指标的实质业务短语起笔" in agenda_retro_fmt

    # 7. 议题模式下加载已定制的 exchange_forum：命中 resources/agenda_templates/zh/exchange_forum.md
    agenda_ef_fmt = resolve_agenda_template_format("exchange_forum")
    assert scan_fixed_bracket_literals(agenda_ef_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_ef_fmt
    assert "正文统一以反映具体业务实体或事实要点的实质业务短语起笔" in agenda_ef_fmt

    # 8. 议题模式下加载已定制的 class_transcript：命中 resources/agenda_templates/zh/class_transcript.md
    agenda_ct_fmt = resolve_agenda_template_format("class_transcript")
    assert scan_fixed_bracket_literals(agenda_ct_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_ct_fmt
    assert "正文统一以反映具体概念、定理或推演主题的实质业务短语起笔" in agenda_ct_fmt

    # 9. 议题模式下加载已定制的 special_lecture：命中 resources/agenda_templates/zh/special_lecture.md
    agenda_sl_fmt = resolve_agenda_template_format("special_lecture")
    assert scan_fixed_bracket_literals(agenda_sl_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_sl_fmt
    assert "正文统一以反映核心观点或论证要素的实质业务短语起笔" in agenda_sl_fmt

    # 10. 议题模式下加载已定制的 group_seminar：命中 resources/agenda_templates/zh/group_seminar.md
    agenda_gs_fmt = resolve_agenda_template_format("group_seminar")
    assert scan_fixed_bracket_literals(agenda_gs_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_gs_fmt
    assert "正文统一以反映发言人或核心论述的实质业务短语起笔" in agenda_gs_fmt

    # 11. 议题模式下加载已定制的 research_dialogue：命中 resources/agenda_templates/zh/research_dialogue.md
    agenda_rd_fmt = resolve_agenda_template_format("research_dialogue")
    assert scan_fixed_bracket_literals(agenda_rd_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_rd_fmt
    assert "正文统一以反映具体业务模块或痛点诉求的实质短语起笔" in agenda_rd_fmt

    # 12. 议题模式下加载已定制的 interview_transcript：命中 resources/agenda_templates/zh/interview_transcript.md
    agenda_it_fmt = resolve_agenda_template_format("interview_transcript")
    assert scan_fixed_bracket_literals(agenda_it_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_it_fmt
    assert "正文统一以反映具体事件、心路历程或核心观点的实质短语起笔" in agenda_it_fmt

    # 13. 议题模式下加载已定制的 knowledge_memo：命中 resources/agenda_templates/zh/knowledge_memo.md
    agenda_km_fmt = resolve_agenda_template_format("knowledge_memo")
    assert scan_fixed_bracket_literals(agenda_km_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_km_fmt
    assert "正文统一以反映具体概念、理论要素或知识分项的实质短语起笔" in agenda_km_fmt

    # 14. 议题模式下加载已定制的 legal_advisory：命中 resources/agenda_templates/zh/legal_advisory.md
    agenda_la_fmt = resolve_agenda_template_format("legal_advisory")
    assert scan_fixed_bracket_literals(agenda_la_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_la_fmt
    assert "每项统一以反映关键节点、涉案主体或争议行为的实质短语起笔" in agenda_la_fmt
    assert "每项统一以「**分析维度**：法规依据与定调结论」起笔" in agenda_la_fmt
    assert "以列表符「- 」直接列出具体行动事项" in agenda_la_fmt

    # 15. 议题模式下加载已定制的 media_briefing：命中 resources/agenda_templates/zh/media_briefing.md
    agenda_mb_fmt = resolve_agenda_template_format("media_briefing")
    assert scan_fixed_bracket_literals(agenda_mb_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_mb_fmt
    assert "正文统一以反映具体业务动作或成果的实质短语起笔" in agenda_mb_fmt
    assert "具体问答交互下沉至「Q&A环节」" in agenda_mb_fmt
    assert "(现场有互动问答才呈现，若全场无互动问答则本栏整体自适应隐去)" in agenda_mb_fmt

    # 16. 议题模式下加载已定制的 government_bulletin：命中 resources/agenda_templates/zh/government_bulletin.md
    agenda_gb_fmt = resolve_agenda_template_format("government_bulletin")
    assert scan_fixed_bracket_literals(agenda_gb_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_gb_fmt
    assert "正文统一以反映具体政策或规划的实质短语起笔" in agenda_gb_fmt
    assert "重要政策法规与核心量化数据自然加粗" in agenda_gb_fmt

    # 17. 议题模式下加载已定制的 media_qa_session：命中 resources/agenda_templates/zh/media_qa_session.md
    agenda_mq_fmt = resolve_agenda_template_format("media_qa_session")
    assert scan_fixed_bracket_literals(agenda_mq_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_mq_fmt
    assert "提问行「**提问方**：提问核心焦点」紧随回答行「**答复方**：明确结论与政策事实依据」成对展开" in agenda_mq_fmt
    assert "## [信息澄清与表态]" in agenda_mq_fmt

    # 18. 议题模式下加载已定制的 conversation_transcript：命中 resources/agenda_templates/zh/conversation_transcript.md
    agenda_ct_fmt = resolve_agenda_template_format("conversation_transcript")
    assert scan_fixed_bracket_literals(agenda_ct_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_ct_fmt
    assert "正文统一以反映发言人或核心观点的实质短语起笔" in agenda_ct_fmt
    assert "①「### 达成共识」" in agenda_ct_fmt
    assert "②「### 存有分歧」" in agenda_ct_fmt

    # 19. 议题模式下加载已定制的 site_visit_tour：命中 resources/agenda_templates/zh/site_visit_tour.md
    agenda_sv_fmt = resolve_agenda_template_format("site_visit_tour")
    assert scan_fixed_bracket_literals(agenda_sv_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_sv_fmt
    assert "按「- **看点名称**：具体解说要点与专业数据」逐条展开" in agenda_sv_fmt
    assert "清单化提炼参访所获认知增量、实践启示与转化建议" in agenda_sv_fmt

    # 20. 议题模式下加载已定制的 home_school_liaison：命中 resources/agenda_templates/zh/home_school_liaison.md
    agenda_hsl_fmt = resolve_agenda_template_format("home_school_liaison")
    assert scan_fixed_bracket_literals(agenda_hsl_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_hsl_fmt
    assert "每项以「- **观察维度/表现领域**」独立成行起笔" in agenda_hsl_fmt
    assert "每项以「- **探讨主题/关注焦点**」独立成行起笔" in agenda_hsl_fmt

    # 21. 议题模式下加载未设议题驱动的模板（如 contract_vetting）：平滑回退普通模板
    fallback_fmt = resolve_agenda_template_format("contract_vetting")
    orig_fmt = resolve_template_format("contract_vetting")
    assert fallback_fmt == orig_fmt
