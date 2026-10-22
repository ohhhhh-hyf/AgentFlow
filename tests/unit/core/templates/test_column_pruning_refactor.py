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
