"""minutes_trace 任务重构单元测试：平实两级结构、议题内涵匹配、HTML 渲染兼容性。

用法::
    pytest tests/test_minutes_trace_refactor.py
"""
from __future__ import annotations

import re

from domains.meeting.tasks.minutes_trace.align import (
    _build_topic_details,
    _topic_score,
    _best_segment,
    backfill_alignments,
    stamp_minutes,
    segment_minutes,
)
from domains.meeting.tasks.minutes_trace.html import trace_review_html
from domains.meeting.tasks.minutes_trace.structure import (
    bulletize_minutes,
    collect_people,
    topic_headings,
)


SAMPLE_NEW_MINUTES = """# 会议纪要：电商大促系统稳定性与履约改造评审会

## 会议概况
本次会议主要对齐 618 大促前网关稳定性及订单履约改造方案。会议确认了采用 Redis 二级缓存方案解决鉴权穿透问题，通过了履约状态异步解耦设计，确定全链路改造于 5 月 20 日前完成预发压测与灰度发版。

## 网关鉴权改造与缓存选型
- 当前鉴权网关在高峰期 QPS 超过 5000 时出现 15% 的 CPU 抖动，排查确认为 JWT 本地校验缓存穿透导致的重复解密。
- 架构组确认采用 Redis 二级缓存替代本地 Guava 缓存，暂不进行机器物理扩容。
- 张三负责在 4 月 10 日前完成改造，并在预发环境完成全链路压测与降级预案。
- 下游营销服务尚未接入新鉴权 SDK，若未按期联调将直接影响大促切流。

## 订单履约状态机异步化
- 履约状态更新目前为同步事务调用，高峰期死锁率约为 0.3%，影响支付成功回调。
- 会上一致同意引入消息队列进行状态变更削峰，履约状态机只做最终一致性校验。
- 李四负责消息队列消费重试机制设计，计划于 4 月 15 日提测。
"""

SAMPLE_TRANSCRIPT = """
张三：网关在压测时 QPS 达到 5000 之后 CPU 抖动达到 15%，主要是 JWT 本地缓存穿透。
李总：那就定下来，用 Redis 做二级缓存，不用 Guava 了，也不扩机器。张三你在 4 月 10 日前完成。
王五：营销服务还没接新 SDK，联调要是拖了会影响切流。
李四：订单履约这块死锁率 0.3%，我们改成 MQ 异步削峰，我 4 月 15 日前提测。
"""

SAMPLE_UNDERSTANDING = {
    "topics": [
        {
            "topic_id": "topic_01",
            "title": "网关鉴权改造与缓存选型",
            "discussion": ["QPS 5000 时 CPU 抖动 15%", "JWT 本地缓存穿透"],
            "decisions": ["采用 Redis 二级缓存替代 Guava 缓存", "不进行机器扩容"],
            "actions": [
                {"task": "完成二级缓存改造与全链路压测", "assignee": "张三", "deadline": "4月10日"}
            ],
            "risks": [
                {"risk": "营销服务未接入新 SDK 影响联调切流"}
            ],
        },
        {
            "topic_id": "topic_02",
            "title": "订单履约状态机异步化",
            "discussion": ["履约状态同步调用死锁率 0.3%"],
            "decisions": ["引入消息队列削峰解耦"],
            "actions": [
                {"task": "消息队列消费重试机制设计并提测", "assignee": "李四", "deadline": "4月15日"}
            ],
            "risks": [],
        },
    ]
}


def test_structure_topic_headings() -> None:
    headings = topic_headings(SAMPLE_NEW_MINUTES)
    assert headings == ["网关鉴权改造与缓存选型", "订单履约状态机异步化"]
    assert "会议概况" not in headings


def test_structure_bulletize_minutes() -> None:
    text = (
        "## 会议概况\n"
        "这是第一句。这是第二句。\n\n"
        "## 议题一\n"
        "这是要点一。这是要点二。\n"
    )
    bulletized = bulletize_minutes(text)
    # 会议概况成段保留，不添加 - 列表前缀
    assert "- 这是第一句" not in bulletized
    assert "这是第一句。这是第二句。" in bulletized
    # 议题一正常拆分为 - 列表条目
    assert "- 这是要点一。" in bulletized
    assert "- 这是要点二。" in bulletized


def test_build_topic_details() -> None:
    details = _build_topic_details(SAMPLE_UNDERSTANDING)
    assert "网关鉴权改造与缓存选型" in details
    assert "订单履约状态机异步化" in details
    
    gw_items = details["网关鉴权改造与缓存选型"]
    assert any("Redis" in it for it in gw_items)
    assert any("张三" in it for it in gw_items)
    assert any("营销服务" in it for it in gw_items)


def test_topic_score_with_topic_details() -> None:
    details = _build_topic_details(SAMPLE_UNDERSTANDING)
    titles = ["网关鉴权改造与缓存选型", "订单履约状态机异步化"]

    # 包含议题内行动项人名与任务，但未直接出现标题中的完整字眼
    score_gw = _topic_score("张三负责4月10日前交付", "网关鉴权改造与缓存选型", titles, details)
    score_order = _topic_score("张三负责4月10日前交付", "订单履约状态机异步化", titles, details)
    assert score_gw > score_order


def test_best_segment_matching() -> None:
    details = _build_topic_details(SAMPLE_UNDERSTANDING)
    titles = ["网关鉴权改造与缓存选型", "订单履约状态机异步化"]
    segments = segment_minutes(SAMPLE_NEW_MINUTES)

    best_pool = _best_segment("李四负责MQ重试并在4月15日提测", segments, titles, details)
    assert best_pool is not None
    assert any("李四" in sent for sent in best_pool)


def test_backfill_and_stamp_minutes() -> None:
    keypoints = [
        "网关QPS超过5000时CPU抖动15%",
        "张三负责4月10日前完成改造",
    ]
    notes = [
        ("营销服务未接入新SDK", "必须尽快推动"),
    ]
    alignments = backfill_alignments(
        [],
        SAMPLE_NEW_MINUTES,
        SAMPLE_TRANSCRIPT,
        keypoints,
        notes,
        topic_titles=["网关鉴权改造与缓存选型", "订单履约状态机异步化"],
        understanding=SAMPLE_UNDERSTANDING,
    )
    assert len(alignments) >= 2
    stamped = stamp_minutes(SAMPLE_NEW_MINUTES, alignments)
    assert "###[【" in stamped
    assert "- 当前鉴权网关在高峰期 QPS 超过 5000" in stamped


def test_trace_review_html_render() -> None:
    # 模拟打钉后的 Markdown
    pinned_md = (
        SAMPLE_NEW_MINUTES.replace(
            "排查确认为 JWT 本地校验缓存穿透导致的重复解密。",
            "排查确认为 JWT 本地校验缓存穿透导致的重复解密。###[【网关高并发抖动排查】]",
        )
    )
    html = trace_review_html(pinned_md, title="测试溯源纪要")
    assert "<title>会议溯源</title>" in html
    assert "<h1>会议溯源</h1>" in html
    assert '<div class="ck-doc-meta">' not in html
    assert "客观会议纪要" not in html
    assert '<h2 class="ck-doc-h2">会议概况</h2>' in html
    assert '<h2 class="ck-doc-h2">网关鉴权改造与缓存选型</h2>' in html
    assert 'class="ck-cite-ref"' in html
    assert 'class="ck-ev' in html
    assert "网关高并发抖动排查" in html
    assert "adjustTraceFolding" in html
    assert "ck-ev-more" in html
    assert "查看更多溯源材料" in html


def test_trace_review_html_without_pins() -> None:
    html = trace_review_html(SAMPLE_NEW_MINUTES)
    assert "<title>会议溯源</title>" in html


SAMPLE_FLAT_UNDERSTANDING = {
    "meeting_brief": "618大促前网关稳定性及订单履约改造方案评审会",
    "meeting_purpose": "对齐大促稳定性技术方案与排期",
    "speakers": [
        {"name": "张三", "role": "架构师", "org": "架构组"},
        {"name": "李四", "role": "开发负责人", "org": "履约组"},
        {"name": "李总", "role": "负责人", "org": "技术部"},
        {"name": "王五", "role": "营销负责人", "org": "营销组"},
    ],
    "topics": [
        {
            "module": "核心网关架构优化",
            "title": "网关鉴权改造与缓存选型",
            "discussion": "网关在压测时 QPS 达到 5000 之后 CPU 抖动达到 15%，主要是 JWT 本地缓存穿透",
            "key_points": [
                "网关高峰期 QPS 超过 5000 时 CPU 抖动达 15%",
                "排查确认为 JWT 本地缓存穿透导致的重复解密",
                "架构组确认采用 Redis 二级缓存替代 Guava 缓存",
                "本次大促暂不进行机器物理扩容",
            ],
            "conclusion": "采用 Redis 二级缓存方案，张三负责 4 月 10 日前完成",
            "participants": ["张三", "李总", "王五"],
        },
        {
            "module": "交易履约改造",
            "title": "订单履约状态机异步化",
            "discussion": "履约状态更新目前为同步事务调用，高峰期死锁率约为 0.3%，改成 MQ 异步削峰",
            "key_points": [
                "履约状态同步调用死锁率 0.3%",
                "一致同意引入消息队列削峰解耦，履约状态机做最终一致性校验",
                "李四负责消息队列重试机制设计并提测",
            ],
            "conclusion": "引入 MQ 异步削峰，李四 4 月 15 日前提测",
            "participants": ["李四"],
        },
    ],
    "decisions": [
        "采用 Redis 二级缓存替代 Guava 缓存，暂不扩机器",
        "订单履约引入消息队列削峰解耦",
    ],
    "risks": [
        "营销服务未接入新 SDK 影响联调切流",
    ],
    "action_hints": [
        {
            "action": "完成二级缓存改造并在预发完成压测与降级预案",
            "owner": "张三",
            "timing": "4月10日前",
            "condition": None,
            "topic": "网关鉴权改造与缓存选型",
            "kind": "assignment",
            "evidence": "张三你在 4 月 10 日前完成。",
        },
        {
            "action": "消息队列消费重试机制设计并提测",
            "owner": "李四",
            "timing": "4月15日前",
            "condition": None,
            "topic": "订单履约状态机异步化",
            "kind": "assignment",
            "evidence": "我 4 月 15 日前提测。",
        },
    ],
    "risk_hints": [
        {
            "risk": "营销服务未接入新 SDK 影响大促联调切流",
            "topic": "网关鉴权改造与缓存选型",
            "signal_type": "dependency",
            "severity_evidence": "联调要是拖了会影响切流",
            "impact": "影响大促切流",
            "mitigation": None,
            "owner": "王五",
            "evidence": "营销服务还没接新 SDK，联调要是拖了会影响切流。",
        }
    ],
    "dependencies": [
        "营销服务接入新 SDK 是切流的前置依赖",
    ],
}


def test_flat_structure_build_topic_details() -> None:
    details = _build_topic_details(SAMPLE_FLAT_UNDERSTANDING)
    assert "网关鉴权改造与缓存选型" in details
    assert "订单履约状态机异步化" in details

    gw_items = details["网关鉴权改造与缓存选型"]
    # key_points 命中
    assert any("Redis" in it for it in gw_items)
    # action_hints 命中
    assert any("张三" in it for it in gw_items)
    # risk_hints 命中
    assert any("营销服务" in it for it in gw_items)


def test_flat_structure_topic_score_and_routing() -> None:
    details = _build_topic_details(SAMPLE_FLAT_UNDERSTANDING)
    titles = ["网关鉴权改造与缓存选型", "订单履约状态机异步化"]
    segments = segment_minutes(SAMPLE_NEW_MINUTES)

    # 包含平铺 action_hints 中人名与时限
    score_gw = _topic_score("张三负责4月10日前交付", "网关鉴权改造与缓存选型", titles, details)
    score_order = _topic_score("张三负责4月10日前交付", "订单履约状态机异步化", titles, details)
    assert score_gw > score_order

    # best_segment 精准寻段
    best_pool = _best_segment("李四负责4月15日MQ重试机制提测", segments, titles, details)
    assert best_pool is not None
    assert any("李四" in sent for sent in best_pool)


def test_flat_structure_backfill_and_stamp() -> None:
    keypoints = [
        "网关QPS超过5000时CPU抖动15%",
        "张三负责4月10日前完成改造",
    ]
    notes = [
        ("营销服务未接入新SDK", "必须尽快推动"),
    ]
    alignments = backfill_alignments(
        [],
        SAMPLE_NEW_MINUTES,
        SAMPLE_TRANSCRIPT,
        keypoints,
        notes,
        topic_titles=["网关鉴权改造与缓存选型", "订单履约状态机异步化"],
        understanding=SAMPLE_FLAT_UNDERSTANDING,
    )
    assert len(alignments) >= 2
    stamped = stamp_minutes(SAMPLE_NEW_MINUTES, alignments)
    assert "###[【" in stamped
    assert "- 当前鉴权网关在高峰期 QPS 超过 5000" in stamped


def test_flat_structure_collect_people() -> None:
    people = collect_people(SAMPLE_FLAT_UNDERSTANDING, SAMPLE_TRANSCRIPT)
    assert "张三" in people
    assert "李四" in people
    assert "王五" in people


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__]))


