import json
import pytest
from core.templates.router._placeholder import _prune_context_for_column

def test_objective_meeting_noise_filtering_without_user_profile():
    """验证普通客观会议在无用户画像(key_needles为空)时，依然能正确过滤行政噪音并保留业务技术方案。"""
    understanding = {
        "meeting_purpose": "核心业务系统架构演进研讨",
        "meeting_brief": "讨论了网关高性能演进与财务发票报销事宜",
        "topics": [
            {
                "title": "高并发网关长连接优化",
                "module": "网关架构",
                "key_metrics": ["P99≤20ms", "单机承载50万并发"],
                "decisions": ["原则上同意采用Netty原生零拷贝方案"],
                "discussion": "何总详细阐述了Netty零拷贝在内核态与用户态切换上的性能优势，全场达成技术共识并排定下月灰度。",
                "key_points": ["内核态零拷贝技术演进", "双麦降噪时延控制在10ms内"],
            },
            {
                "title": "三季度团建活动与发票报销通知",
                "module": "行政事务",
                "key_metrics": [],
                "decisions": ["周五前贴票提交财务"],
                "discussion": "行政人员通报了发票报销规则和考勤打卡升级事宜。",
                "key_points": ["发票贴票规范", "打卡时间"],
            },
        ],
    }

    draft = {
        "headline": "网关架构研讨会纪要",
        "executive_summary": [
            "会议聚焦高并发网关架构演进，明确了零拷贝技术路线与下月灰度排期。"
        ],
        "key_decisions": ["确定采用Netty零拷贝方案"],
    }

    raw_transcript = (
        "何总 10:00:10\n我们重点讨论高并发网关的零拷贝优化，必须把P99控制在20ms以内。\n"
        "李工 10:05:00\n方案已经过压测，单机可以稳定支撑50万并发。\n"
        "行政小王 10:30:00\n插播一下，大家记得今天下班前把发票贴好交财务进行报销，考勤打卡系统今晚升级。\n"
        "何总 10:32:00\n好的，技术方案大家无异议就按此推进。\n"
    )

    # 构造客观普通全员会议上下文（无任何用户画像）
    context = (
        "视角模式：objective\n"
        "objective_perspective：True\n\n"
        f"会议理解：\n{json.dumps(understanding, ensure_ascii=False)}\n\n"
        f"已批准纪要草稿：\n{json.dumps(draft, ensure_ascii=False)}\n\n"
        f"会议原文：\n{raw_transcript}\n\n"
        "纪要审核结论：\n{\"decision\": \"approve\"}\n"
    )

    # 1. 测试业务研讨栏（如【业务进展】/【方案陈述】）
    pruned_biz = _prune_context_for_column(context, "", title="业务进展", hint="")

    # 核心业务技术细节与量化指标必须保留
    assert "高并发网关长连接优化" in pruned_biz
    assert "P99≤20ms" in pruned_biz
    assert "单机承载50万并发" in pruned_biz
    assert "Netty原生零拷贝方案" in pruned_biz
    assert "全场达成技术共识并排定下月灰度" in pruned_biz

    # 行政噪音必须被剔除
    assert "发票报销通知" not in pruned_biz
    assert "发票贴好交财务进行报销" not in pruned_biz
    assert "考勤打卡系统今晚升级" not in pruned_biz

    # 2. 测试未知/新栏目（终极安全兜底）
    pruned_unknown = _prune_context_for_column(context, "", title="核心架构技术方案细节", hint="")
    assert "高并发网关长连接优化" in pruned_unknown
    assert "P99≤20ms" in pruned_unknown
    assert "发票报销通知" not in pruned_unknown
    assert "考勤打卡" not in pruned_unknown

def test_long_transcript_safety_truncation():
    """验证超过3000字的长文本原文被严格截断，绝不发生3万字长文裸传。"""
    draft = {"headline": "测试", "executive_summary": ["摘要"]}
    understanding = {"topics": [{"title": "业务议题", "discussion": "正常讨论"}]}
    long_raw = "技术讨论长段落内容。\n" * 500  # 约 5500 字

    context = (
        "视角模式：objective\n"
        "objective_perspective：True\n\n"
        f"会议理解：\n{json.dumps(understanding, ensure_ascii=False)}\n\n"
        f"已批准纪要草稿：\n{json.dumps(draft, ensure_ascii=False)}\n\n"
        f"会议原文：\n{long_raw}\n\n"
        "纪要审核结论：\n{\"decision\": \"approve\"}\n"
    )

    pruned = _prune_context_for_column(context, "", title="任意未知栏目", hint="")
    # 验证原文长尾被截断，且带有说明标记
    assert "后文各模块细节讨论略" in pruned
    assert len(pruned) < 3500

def test_overview_column_prunes_executive_summary_to_first_item():
    """验证总述概览类栏目(is_overview_col)裁剪时，草稿executive_summary被严格截断为仅保留首项宏观概括。"""
    draft = {
        "headline": "年度投资理念交流会",
        "executive_summary": [
            "第一段：本次讲座为基金经理肖楠面向机构投资者的宏观框架汇报。",
            "第二段：肖楠介绍了务实派与务虚派的投资理念差异，反对抱团与均值回归。",
            "第三段：肖楠汇报了互联网、财富管理、新消费和高端制造四大方向的布局。"
        ],
        "key_decisions": ["坚持务实投资框架"]
    }
    understanding = {
        "meeting_purpose": "年度投资汇报",
        "meeting_brief": "投资框架与行业反思",
        "topics": [{"title": "投资理念", "discussion": "宏观与微观"}]
    }

    context = (
        "视角模式：objective\n"
        "objective_perspective：True\n\n"
        f"会议理解：\n{json.dumps(understanding, ensure_ascii=False)}\n\n"
        f"已批准纪要草稿：\n{json.dumps(draft, ensure_ascii=False)}\n\n"
        "纪要审核结论：\n{\"decision\": \"approve\"}\n"
    )

    pruned = _prune_context_for_column(context, "", title="讲座概况", hint="单段概括，约 250–350 字")

    # 验证只保留了第一段宏观概括
    assert "第一段：本次讲座为基金经理肖楠面向机构投资者的宏观框架汇报" in pruned
    # 验证后续第二段、第三段具体论证已被严格剔除，杜绝输入多段诱导模型输出多段
    assert "第二段：肖楠介绍了务实派与务虚派" not in pruned
    assert "第三段：肖楠汇报了互联网" not in pruned


def test_minutes_validation_auto_fills_missing_history_comparison():
    """验证当LLM因无需编写而漏输出history_comparison时，Minutes.validate零报错自动补空列表，避免7秒二次重试。"""
    from domains.meeting.models_generated import Minutes

    raw_data_without_history_comparison = {
        "headline": "手机常用APP与音乐偏好交流讨论",
        "executive_summary": ["本次讨论为多人参与的闲聊式交流，围绕常用APP展开。"],
        "key_decisions": ["达成共识"],
        "personally_relevant_points": ["小李跟进"],
        "risks_and_blockers": [],
        "unresolved_questions": []
        # 注意：此处故意缺少 history_comparison 键
    }

    minutes_obj = Minutes.validate(raw_data_without_history_comparison)
    assert minutes_obj.headline == "手机常用APP与音乐偏好交流讨论"
    assert minutes_obj.history_comparison == []


def test_prompts_overview_word_budget_and_mapping_rules():
    """验证Prompt契约中首项字数已对齐250-350字，且普通模板渲染Prompt包含总述栏映射规约。"""
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_OBJECTIVE_GENERATION_PROMPT,
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_RENDER_TEMPLATE_PROMPT,
    )

    # 1. 验证生成Prompt中首项字数约束已对齐为 250–350 字
    assert "默认 250–350 字" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "约 250–350 字" in MINUTES_AGENDA_GENERATION_PROMPT

    # 2. 验证普通模板渲染Prompt中已补齐概括总述类栏目的单段映射规约
    assert "【栏目语义自适应映射】" in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "概括总述类栏目" in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "映射草稿 executive_summary 的首项" in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "严禁分多段输出" in MINUTES_RENDER_TEMPLATE_PROMPT

