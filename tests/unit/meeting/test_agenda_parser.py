"""tests/unit/meeting/test_agenda_parser.py -- 议程解析器（文本/表格/缩进/OCR）单元测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import docx
import pytest

from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    clean_presenter_names,
    parse_agenda_text,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    group_transcript_blocks,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    AgendaMinutesAgent,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_render import (
    AgendaMinutesRender,
)
from infra.exporters.html.agenda_minutes import (
    format_agenda_minutes_markdown,
    render_agenda_minutes_html,
)

PROJECT_ROOT = Path(__file__).resolve().parent
while PROJECT_ROOT.parent != PROJECT_ROOT and not (PROJECT_ROOT / "domains").exists():
    PROJECT_ROOT = PROJECT_ROOT.parent

AGENDA_DIR = (
    PROJECT_ROOT / "data" / "1" / "agenda"
    if (PROJECT_ROOT / "data" / "1" / "agenda").exists()
    else PROJECT_ROOT / "agenda"
)

def test_clean_presenter_names():
    """测试汇报人姓名清洗逻辑。"""
    assert clean_presenter_names("汇报人: 赵鑫岳 00585440") == ["赵鑫岳"]
    assert clean_presenter_names("沙彬斌; 陈啟锴") == ["沙彬斌", "陈啟锴"]
    assert clean_presenter_names("陆敬怡; 林宇珂; 赖朝辉") == ["陆敬怡", "林宇珂", "赖朝辉"]
    assert clean_presenter_names("汇报人: 林宇珂 00939670 陆敬怡 00841266") == ["林宇珂", "陆敬怡"]
    assert clean_presenter_names("索勋飞(委托高雄)") == ["索勋飞"]
    assert clean_presenter_names("非公开") == []

def test_agenda_parser_standard_numbered_list():
    """测试商评1议程解析（含元数据与双语表头）。"""
    txt_path = AGENDA_DIR / "test1" / "商评1.txt"
    if not txt_path.is_file():
        pytest.skip("商评1.txt not found")
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    assert "智慧域商用发布评审" in plan.meta.theme
    assert "2026/06/15" in plan.meta.date_time
    assert "全程与会人" in plan.meta.attendees
    assert len(plan.items) == 4

    assert plan.items[0].seq == "01"
    assert "小艺慧记" in plan.items[0].title
    assert plan.items[0].presenters == ["申家坤"]

    assert plan.items[1].seq == "02"
    assert "翻译海外" in plan.items[1].title
    assert plan.items[1].presenters == ["刘畅"]

    assert plan.items[2].seq == "03"
    assert "HAG" in plan.items[2].title
    assert set(plan.items[2].presenters) == {"沙彬斌", "陈啟锴"}

    assert plan.items[3].seq == "04"
    assert "SpeechASR" in plan.items[3].title
    assert set(plan.items[3].presenters) == {"陆敬怡", "林宇珂", "赖朝辉"}

def test_agenda_parser_multiline_and_tab_delimiters():
    """测试商评2、小艺委例会、月度洞察会的议程解析。"""
    # Test 2: 9 items
    t2_path = AGENDA_DIR / "test2" / "商评2.txt"
    if t2_path.is_file():
        plan2 = parse_agenda_text(t2_path.read_text(encoding="utf-8"))
        assert len(plan2.items) == 9
        assert plan2.items[0].presenters == ["赵鑫岳"]
        assert plan2.items[2].presenters == ["武思华"]
        assert plan2.items[5].presenters == ["林宇珂", "陆敬怡"]

    # Test 3: 4 items
    t3_path = AGENDA_DIR / "test3" / "小艺语音技术委员会.txt"
    if t3_path.is_file():
        plan3 = parse_agenda_text(t3_path.read_text(encoding="utf-8"))
        assert len(plan3.items) == 4
        assert plan3.items[0].presenters == ["周径"]
        assert plan3.items[1].presenters == ["张子晗"]
        assert plan3.items[3].presenters == ["卢凌峰"]

    # Test 4: 3 items
    t4_path = AGENDA_DIR / "test4" / "月度洞察会.txt"
    if t4_path.is_file():
        plan4 = parse_agenda_text(t4_path.read_text(encoding="utf-8"))
        assert len(plan4.items) == 3
        assert plan4.items[0].presenters == ["王海涛"]
        assert plan4.items[1].presenters == ["刘雨桉"]
        assert plan4.items[2].presenters == ["朱启源"]

def test_agenda_parser_bullet_fallback():
    """测试无表格时的序号列表降级解析。"""
    raw_list = """
    会议主题：技术前沿研讨例会
    1. 具身智能世界模型前沿洞察 汇报人：李博士
    2. 多模态长序列端侧推理优化 汇报人：王工
    3. 强化学习在声学降噪中的实践 汇报人：张研究员
    """
    plan = parse_agenda_text(raw_list)
    assert plan.meta.theme == "技术前沿研讨例会"
    assert len(plan.items) == 3
    assert plan.items[0].seq == "01"
    assert "具身智能" in plan.items[0].title
    assert plan.items[0].presenters == ["李博士"]
    assert plan.items[1].presenters == ["王工"]
    assert plan.items[2].presenters == ["张研究员"]

def test_agenda_parser_markdown_table_and_tabs():
    """测试标准 Markdown 表格与 Tab 制表符文本的高保真解析。"""
    md_table = """
| 编号 | 议题名称 | 时长 | 起止时间 | 汇报人 | 纪要人 | 议题参与人 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 小艺慧记 CeliaMinutesService 1.4.5.500 版本发布商用版本 | 15min | 16:00-16:15 | 申家坤 | 申家坤 | 方思邈；李腾飞；郑本令 |
| 2 | 翻译海外 HiTranslationService 21.1.1.300 商用版本发布 | 15min | 16:15-16:30 | 刘畅 | 刘畅 | 陈坤；赵磊；陈冬阳 |
"""
    plan = parse_agenda_text(md_table)
    assert len(plan.items) == 2
    assert plan.items[0].seq == "01"
    assert "小艺慧记" in plan.items[0].title
    assert plan.items[0].presenters == ["申家坤"]
    assert plan.items[0].duration == "15min"
    assert plan.items[0].time_range == "16:00-16:15"

    tab_text = "序号\t议题名称\t时长\t汇报人\n1\t大模型推理优化\t30分钟\t张三\n2\tAgent长期记忆\t30分钟\t李四"
    plan_tab = parse_agenda_text(tab_text)
    assert len(plan_tab.items) == 2
    assert plan_tab.items[0].seq == "01"
    assert plan_tab.items[0].title == "大模型推理优化"
    assert plan_tab.items[0].presenters == ["张三"]

    line_text = "1 智能跃迁：智能体RSI递归自我演进技术洞察 汇报人：刘雨桉\n2 AI infra优化实践 汇报人：朱启源"
    plan_line = parse_agenda_text(line_text)
    assert len(plan_line.items) == 2
    assert plan_line.items[0].seq == "01"
    assert "智能跃迁" in plan_line.items[0].title
    assert plan_line.items[0].presenters == ["刘雨桉"]

def test_ocr_serverocr_fallback_to_rapidocr(monkeypatch):
    """测试 .env 中配置 serverocr 时，服务器不可用自动降级兜底至 RapidOCR。"""
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        pytest.skip("rapidocr_onnxruntime not installed")

    from infra.ocr.engines import run_ocr_subprocess

    monkeypatch.setenv("OCR_ENGINE", "serverocr")
    monkeypatch.setenv("SERVER_OCR_URL", "http://127.0.0.1:59999/nonexistent")

    img_path = AGENDA_DIR / "test1" / "商评1.png"
    if not img_path.is_file():
        pytest.skip("商评1.png not found")

    res = run_ocr_subprocess(str(img_path))
    assert res.get("engine") == "rapidocr"
    assert len(res.get("lines", [])) > 0

def test_agenda_types_registry_and_specs():
    """测试 9 大会议类型注册表与 Spec 规范定义。"""
    from domains.meeting.tasks.agenda_minutes.types import (
        AGENDA_TYPE_REGISTRY,
        get_agenda_type_spec,
    )
    from domains.meeting.tasks.agenda_minutes.prompts import build_single_item_prompt

    assert len(AGENDA_TYPE_REGISTRY) == 9
    expected_types = [
        "decision_approval",
        "review_selection",
        "planning_strategy",
        "alignment_consensus",
        "info_sync",
        "retrospective",
        "brainstorming",
        "release_broadcast",
        "knowledge_share",
    ]
    for tid in expected_types:
        spec = get_agenda_type_spec(tid)
        assert spec.type_id == tid
        assert spec.type_name
        assert spec.core_purpose
        assert spec.core_output
        assert len(spec.pillars) == 4
        guidance = spec.format_prompt_guidance()
        assert spec.type_name in guidance
        assert "1. 背景与目标" in guidance
        assert "4. 后续行动" in guidance

    # 测试未知类型安全降级
    fallback_spec = get_agenda_type_spec("non_existent_type")
    assert fallback_spec.type_id == "decision_approval"

    # 测试 build_single_item_prompt 动态拼接
    prompt = build_single_item_prompt(fallback_spec)
    assert "决策审批型" in prompt
    assert "background_and_goals" in prompt
    assert "action_items" in prompt

def test_detect_agenda_type_all_categories():
    """测试基于会议主题与上下文的 9 大类型智能路由器。"""
    from domains.meeting.tasks.agenda_minutes.types import detect_agenda_type

    # 1. 决策审批型
    assert detect_agenda_type("智慧域商用发布评审").type_id == "decision_approval"
    assert detect_agenda_type("关于2026年项目立项与预算审批会").type_id == "decision_approval"

    # 2. 评审选型型
    assert detect_agenda_type("向量数据库技术方案选型评审会").type_id == "review_selection"
    assert detect_agenda_type("大模型基础设施架构评审与供应商评选").type_id == "review_selection"

    # 3. 规划策略型
    assert detect_agenda_type("2026年Q3业务战略与路线图规划会").type_id == "planning_strategy"
    assert detect_agenda_type("年度研发优先级排序与资源规划研讨").type_id == "planning_strategy"

    # 4. 对齐共识型
    assert detect_agenda_type("前后端系统接口契约对齐与联调拉通会").type_id == "alignment_consensus"
    assert detect_agenda_type("跨部门协作职责边界敲定会").type_id == "alignment_consensus"

    # 5. 信息同步型
    assert detect_agenda_type("开发团队周例会及阻塞项同步").type_id == "info_sync"
    assert detect_agenda_type("敏捷迭代每日站会").type_id == "info_sync"

    # 6. 复盘归因型
    assert detect_agenda_type("0618线上突发故障根因分析与复盘会").type_id == "retrospective"
    assert detect_agenda_type("端午大促项目复盘总结会").type_id == "retrospective"

    # 7. 创意发散型
    assert detect_agenda_type("AI原生产品创新头脑风暴工作坊").type_id == "brainstorming"
    assert detect_agenda_type("增长黑客发散创意研讨会").type_id == "brainstorming"

    # 8. 发布传播型
    assert detect_agenda_type("智能终端新一代操作系统全网发布宣贯会").type_id == "release_broadcast"
    assert detect_agenda_type("对外公告与媒体答疑口径统一会").type_id == "release_broadcast"

    # 9. 知识分享型
    assert detect_agenda_type("Agent架构底层原理解析与技术沙龙").type_id == "knowledge_share"
    assert detect_agenda_type("新员工代码规范培训与知识分享").type_id == "knowledge_share"

    # 10. 兜底测试
    assert detect_agenda_type("常规会议讨论").type_id == "decision_approval"

def test_single_agenda_item_model_bi_directional_compat():
    """测试 SingleAgendaItemModel 在 1~5 纯干货字段与老字段之间的双向平滑兼容。"""
    from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import SingleAgendaItemModel

    # 1. 传入全新 1~5 字段
    new_data = {
        "presenter": "刘畅",
        "status_tag": "[原则同意]",
        "target_and_audience": ["申请商用准入许可", "面向评委会"],
        "content_and_evidence": ["双机房热备部署", "时延降至 85ms"],
        "process_and_interaction": ["评委质询故障逃逸，出具演练日志释疑"],
        "conclusion_and_status": "原则同意发布，灰度比例10%内",
        "action_items": [{"owner": "刘畅", "task": "签署核查单", "deadline": "9月30日"}],
    }
    model1 = SingleAgendaItemModel.validate(new_data)
    assert model1.target_and_audience == ["申请商用准入许可", "面向评委会"]
    assert model1.content_and_evidence == ["双机房热备部署", "时延降至 85ms"]
    assert model1.process_and_interaction == ["评委质询故障逃逸，出具演练日志释疑"]
    assert model1.conclusion_and_status == "原则同意发布，灰度比例10%内"
    assert len(model1.action_items) == 1
    # 验证老字段被完全向上兼容填充
    assert model1.proposal_highlights == model1.target_and_audience
    assert model1.deliberation_details["key_metrics"] == model1.content_and_evidence
    assert model1.deliberation_details["feedback_concerns"] == model1.process_and_interaction
    assert model1.resolution == model1.conclusion_and_status
    assert model1.action_commitments == model1.action_items

    # 2. 传入老字段数据，验证自动映射至 1~5 字段
    legacy_data = {
        "presenter": "沙彬斌",
        "status_tag": "[审议通过]",
        "proposal_highlights": ["升级微服务架构"],
        "deliberation_details": {
            "key_metrics": ["吞吐量提升 30%"],
            "feedback_concerns": ["关注内存增长风险"],
        },
        "resolution": "方案通过，按计划上线",
        "action_commitments": [{"owner": "沙彬斌", "task": "压测", "deadline": "下周"}],
    }
    model2 = SingleAgendaItemModel.validate(legacy_data)
    assert model2.target_and_audience == ["升级微服务架构"]
    assert model2.content_and_evidence == ["吞吐量提升 30%"]
    assert model2.process_and_interaction == ["关注内存增长风险"]
    assert model2.conclusion_and_status == "方案通过，按计划上线"
    assert len(model2.action_items) == 1
    assert model2.action_items[0]["owner"] == "沙彬斌"

def test_agenda_parser_table_format_without_presenter_column():
    """验证 test7 议程解析：
    1. 适配表头为 | 序号 | 时间 | 环节 | 内容说明 | 的表结构；
    2. 无汇报人列时正常解析为 5 项，title 为环节，description 为内容说明；
    3. 完整保留何刚总致辞、互动交流、任务令签署与授予、全体合影等核心议程。
    """
    ocr_test7 = """
会议日程表
会议主题：何刚总北研所交流会
会议时间：2026年09月23日9:00—11:00
会议地点：北研所Q1-A031

| 序号 | 时间 | 环节 | 内容说明 |
| :--- | :--- | :--- | :--- |
| 01 | 09:00-09:10 | 视频观看 | 活动开场视频播放 |
| 02 | 09:10-09:30 | 何刚总致辞 | 领导致辞 |
| 03 | 09:30-10:30 | 互动交流 | 现场问答、自由交流与讨论 |
| 04 | 10:30-10:40 | 任务令签署与授予 | 任务令签署仪式及授予环节 |
| 05 | 10:40-10:50 | 全体合影 | 全体参会人员合影留念 |
"""
    plan = parse_agenda_text(ocr_test7)
    assert plan.meta.theme == "何刚总北研所交流会"
    assert len(plan.items) == 5

    assert plan.items[0].seq == "01"
    assert plan.items[0].title == "视频观看"
    assert plan.items[0].description == "活动开场视频播放"
    assert plan.items[0].presenters == []

    assert plan.items[1].seq == "02"
    assert plan.items[1].title == "何刚总致辞"
    assert plan.items[1].description == "领导致辞"

    assert plan.items[2].seq == "03"
    assert plan.items[2].title == "互动交流"
    assert plan.items[2].description == "现场问答、自由交流与讨论"

    assert plan.items[3].seq == "04"
    assert plan.items[3].title == "任务令签署与授予"
    assert plan.items[3].description == "任务令签署仪式及授予环节"

    assert plan.items[4].seq == "05"
    assert plan.items[4].title == "全体合影"
    assert plan.items[4].description == "全体参会人员合影留念"

def test_paddle_ocr_join_row_texts_avoids_name_concatenation():
    """测试 PaddleOCR 同行拼接时，避免将汇报人与记录人无缝粘连为单个姓名。"""
    from infra.ocr.paddle_ocr import _join_row_texts

    # 汇报人与记录人相邻
    merged = _join_row_texts(["陆敬怡;林宇珂;赖朝辉", "王旭"])
    assert merged == "陆敬怡;林宇珂;赖朝辉 王旭"
    assert "赖朝辉王旭" not in merged

    # 带分号结尾的正常列表
    merged_semi = _join_row_texts(["沙彬斌；", "陈啟锴"])
    assert merged_semi == "沙彬斌；陈啟锴"

def test_prepare_agenda_ocr_prompt_text_filters_sidebar_and_preserves_columns():
    """测试 prepare_agenda_ocr_prompt_text 能正确过滤左侧装饰性侧栏标签，并按水平行聚类。"""
    from domains.meeting.tasks.agenda_minutes.agenda_extractor import prepare_agenda_ocr_prompt_text

    raw_lines = [
        {"text": "会议主题：智慧域商用发布评审", "bbox": [[250, 580], [450, 580], [450, 600], [250, 600]]},
        # 左侧装饰标签 (x=50 < 150)
        {"text": "会议议题", "bbox": [[50, 980], [100, 980], [100, 1000], [50, 1000]]},
        {"text": "Agenda", "bbox": [[50, 1010], [100, 1010], [100, 1030], [50, 1030]]},
        # 议题 1 行内各列 (y~950)
        {"text": "1", "bbox": [[255, 950], [270, 950], [270, 970], [255, 970]]},
        {"text": "小艺慧记版本发布", "bbox": [[350, 950], [600, 950], [600, 970], [350, 970]]},
        {"text": "15min", "bbox": [[770, 950], [820, 950], [820, 970], [770, 970]]},
        {"text": "申家坤", "bbox": [[1140, 950], [1190, 950], [1190, 970], [1140, 970]]},
        # 议题 2 行内各列 (y~1010)
        {"text": "翻译海外商用发布", "bbox": [[350, 1010], [600, 1010], [600, 1030], [350, 1030]]},
        {"text": "15min", "bbox": [[770, 1010], [820, 1010], [820, 1030], [770, 1030]]},
        {"text": "刘畅", "bbox": [[1140, 1010], [1190, 1010], [1190, 1030], [1140, 1030]]},
    ]

    res = prepare_agenda_ocr_prompt_text(raw_lines)
    # 验证左侧侧栏装饰性标签已被过滤
    assert "会议议题" not in res
    assert "Agenda" not in res
    # 验证同一行内单元格用 "  |  " 明确分隔
    assert "1  |  小艺慧记版本发布  |  15min  |  申家坤" in res
    assert "翻译海外商用发布  |  15min  |  刘畅" in res

