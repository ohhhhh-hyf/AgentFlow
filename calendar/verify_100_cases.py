"""100 个真实待办 DDL 综合测试集与自动化精度验证脚本。

覆盖 10 大核心维度：
1. 基础自然日相对偏移 (10例)
2. 周偏移与星期几 (10例)
3. 周末语义与推断 (10例)
4. 工作日计算与跳过周末 (10例)
5. 月度边界与日期定位 (10例)
6. 季度与年份边界 (10例)
7. 具体点钟与时间顺延 (10例)
8. 业务模糊时段与时段任务 (10例)
9. 复合组合与跨通道表达 (10例)
10. 否定、待定与无时间表达 (10例)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 将 calendar 加入 sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from agent import run_deadline_agent_sync
from fast_path import try_fast_extract

MEETING_TIME = "2026-10-29 14:30:45"  # 星期四, 2026年Q4

# 100 个完整测试用例定义
TEST_CASES: List[Dict[str, Any]] = [
    # ── Category 1: 基础自然日相对偏移 (10) ──────────────────────────
    {
        "category": "基础自然日相对偏移",
        "raw": "今天",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "明天",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "后天",
        "expected_deadline": "2026/10/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "大后天",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "昨天",
        "expected_deadline": "2026/10/28",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "前天",
        "expected_deadline": "2026/10/27",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "次日",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "3天后",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "5天内",
        "expected_deadline": "2026/11/03",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "基础自然日相对偏移",
        "raw": "10天后",
        "expected_deadline": "2026/11/08",
        "expected_time_slot": None,
        "expected_kind": "date",
    },

    # ── Category 2: 周偏移与星期几 (10) ──────────────────────────
    {
        "category": "周偏移与星期几",
        "raw": "本周五",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "本周一",
        "expected_deadline": "2026/10/26",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "下周一",
        "expected_deadline": "2026/11/02",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "下周二",
        "expected_deadline": "2026/11/03",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "下周三",
        "expected_deadline": "2026/11/04",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "下周四",
        "expected_deadline": "2026/11/05",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "下周五",
        "expected_deadline": "2026/11/06",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "上周三",
        "expected_deadline": "2026/10/21",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "大下周一",
        "expected_deadline": "2026/11/09",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周偏移与星期几",
        "raw": "两周后",
        "expected_deadline": "2026/11/12",
        "expected_time_slot": None,
        "expected_kind": "date",
    },

    # ── Category 3: 周末语义与推断 (10) ──────────────────────────
    {
        "category": "周末语义与推断",
        "raw": "本周末",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "这周末",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "周末",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "下周末",
        "expected_deadline": "2026/11/08",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "大下周末",
        "expected_deadline": "2026/11/15",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "上周末",
        "expected_deadline": "2026/10/25",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "周六",
        "expected_deadline": "2026/10/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "周日",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "下周日",
        "expected_deadline": "2026/11/08",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "周末语义与推断",
        "raw": "下周六",
        "expected_deadline": "2026/11/07",
        "expected_time_slot": None,
        "expected_kind": "date",
    },

    # ── Category 4: 工作日计算与跳过周末 (10) ──────────────────────
    {
        "category": "工作日计算与跳过周末",
        "raw": "1个工作日后",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "2个工作日内",
        "expected_deadline": "2026/11/02",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "2个工作日后",
        "expected_deadline": "2026/11/02",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "3个工作日后",
        "expected_deadline": "2026/11/03",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "3个工作日内",
        "expected_deadline": "2026/11/03",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "4个工作日后",
        "expected_deadline": "2026/11/04",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "5个工作日后",
        "expected_deadline": "2026/11/05",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "7个工作日后",
        "expected_deadline": "2026/11/09",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "10个工作日后",
        "expected_deadline": "2026/11/12",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "工作日计算与跳过周末",
        "raw": "一个工作日内",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },

    # ── Category 5: 月度边界与日期定位 (10) ──────────────────────
    {
        "category": "月度边界与日期定位",
        "raw": "本月底",
        "expected_deadline": "2026/10/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "月底",
        "expected_deadline": "2026/10/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "本月末",
        "expected_deadline": "2026/10/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "下月底",
        "expected_deadline": "2026/11/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "下月初",
        "expected_deadline": "2026/11/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "本月初",
        "expected_deadline": "2026/10/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "本月15号",
        "expected_deadline": "2026/10/15",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "下月10号",
        "expected_deadline": "2026/11/10",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "15号",
        "expected_deadline": "2026/11/15",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "月度边界与日期定位",
        "raw": "11月11号",
        "expected_deadline": "2026/11/11",
        "expected_time_slot": None,
        "expected_kind": "date",
    },

    # ── Category 6: 季度与年份边界 (10) ──────────────────────────
    {
        "category": "季度与年份边界",
        "raw": "本季度末",
        "expected_deadline": "2026/12/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "下季度末",
        "expected_deadline": "2027/03/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "下季度初",
        "expected_deadline": "2027/01/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "Q4末",
        "expected_deadline": "2026/12/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "Q1末",
        "expected_deadline": "2027/03/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "Q2末",
        "expected_deadline": "2027/06/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "Q3末",
        "expected_deadline": "2027/09/30",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "今年年底",
        "expected_deadline": "2026/12/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "年底",
        "expected_deadline": "2026/12/31",
        "expected_time_slot": None,
        "expected_kind": "date",
    },
    {
        "category": "季度与年份边界",
        "raw": "明年初",
        "expected_deadline": "2027/01/01",
        "expected_time_slot": None,
        "expected_kind": "date",
    },

    # ── Category 7: 具体点钟与时间顺延 (10) ──────────────────────────
    {
        "category": "具体点钟与时间顺延",
        "raw": "15:30",
        "expected_deadline": "2026/10/29 15:30",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "10:00",
        "expected_deadline": "2026/10/30 10:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "17:45",
        "expected_deadline": "2026/10/29 17:45",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "3点",
        "expected_deadline": "2026/10/29 15:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "11点",
        "expected_deadline": "2026/10/30 11:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "7点",
        "expected_deadline": "2026/10/30 07:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "下午3点",
        "expected_deadline": "2026/10/29 15:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "上午10点半",
        "expected_deadline": "2026/10/30 10:30",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "下午4点20",
        "expected_deadline": "2026/10/29 16:20",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "具体点钟与时间顺延",
        "raw": "晚上8点",
        "expected_deadline": "2026/10/29 20:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },

    # ── Category 8: 业务模糊时段与时段任务 (10) ────────────────────
    {
        "category": "业务模糊时段与时段任务",
        "raw": "下午",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": "下午",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "上午",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "上午",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "下班前",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": "下班前",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "中午",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "中午",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "晚上",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": "晚上",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "傍晚",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": "下班前",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "明天下班前",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "下班前",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "明天下午",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "下午",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "明天上午",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "上午",
        "expected_kind": "date",
    },
    {
        "category": "业务模糊时段与时段任务",
        "raw": "今天下午",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": "下午",
        "expected_kind": "date",
    },

    # ── Category 9: 复合组合与跨通道表达 (10) ──────────────────────
    {
        "category": "复合组合与跨通道表达",
        "raw": "周五下班前",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "下班前",
        "expected_kind": "date",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "下周三上午10点",
        "expected_deadline": "2026/11/04 10:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "明天下午3点",
        "expected_deadline": "2026/10/30 15:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "今晚",
        "expected_deadline": "2026/10/29",
        "expected_time_slot": "晚上",
        "expected_kind": "date",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "明晚",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "晚上",
        "expected_kind": "date",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "明早",
        "expected_deadline": "2026/10/30",
        "expected_time_slot": "上午",
        "expected_kind": "date",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "会后1小时",
        "expected_deadline": "2026/10/29 15:30",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "会前15分钟",
        "expected_deadline": "2026/10/29 14:15",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "晚上12点",
        "expected_deadline": "2026/10/30 00:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },
    {
        "category": "复合组合与跨通道表达",
        "raw": "午夜",
        "expected_deadline": "2026/10/30 00:00",
        "expected_time_slot": None,
        "expected_kind": "datetime",
    },

    # ── Category 10: 否定、待定与无时间表达 (10) ────────────────────
    {
        "category": "否定与无时间表达",
        "raw": "尽快完成",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "待定",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "暂无",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "没提时间",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "另行通知",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "不限期",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "随缘",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "未提及",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "TBD",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
    {
        "category": "否定与无时间表达",
        "raw": "未说明时间",
        "expected_deadline": None,
        "expected_time_slot": None,
        "expected_kind": "none",
    },
]


def run_verification() -> Dict[str, Any]:
    print("=" * 70)
    print("🚀 开始执行待办时间转换器 100 例工业级综合评测")
    print(f"基准会议时间: {MEETING_TIME} (周四, 2026年Q4)")
    print(f"用例总数: {len(TEST_CASES)} 条")
    print("=" * 70)

    texts = [case["raw"] for case in TEST_CASES]

    # 统计 Fast-Path 命中预判
    fast_hits = 0
    for idx, text in enumerate(texts):
        if try_fast_extract(idx, text) is not None:
            fast_hits += 1
    print(f"📊 架构分流预判: {fast_hits}/{len(texts)} ({fast_hits/len(texts)*100:.1f}%) 命中毫秒级 Fast-Path")
    print(f"                {len(texts)-fast_hits}/{len(texts)} ({ (len(texts)-fast_hits)/len(texts)*100:.1f}%) 降级交由 DeepSeek LLM 分析")
    print("-" * 70)

    # 批量执行 LangGraph Agent
    start_t = time.perf_counter()
    agent_output = run_deadline_agent_sync(
        meeting_start_time=MEETING_TIME,
        texts=texts,
    )
    elapsed = time.perf_counter() - start_t
    print(f"⏱️ 100 条待办全图端到端解析总耗时: {elapsed:.2f} 秒 (平均单条 {elapsed/len(texts)*1000:.2f} 毫秒)")
    print("-" * 70)

    results = agent_output.get("results") or []
    if len(results) != len(TEST_CASES):
        print(f"❌ 严重错误: 输出数量 ({len(results)}) 与输入数量 ({len(TEST_CASES)}) 不一致！")
        return {"total": len(TEST_CASES), "passed": 0, "accuracy": 0.0}

    passed_count = 0
    failed_cases: List[Dict[str, Any]] = []
    category_stats: Dict[str, Dict[str, int]] = {}

    for i, case in enumerate(TEST_CASES):
        actual = results[i]
        cat = case["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0}
        category_stats[cat]["total"] += 1

        # 校验三元组 (deadline, time_slot, kind)
        deadline_ok = actual.get("deadline") == case["expected_deadline"]
        slot_ok = actual.get("time_slot") == case["expected_time_slot"]
        kind_ok = actual.get("kind") == case["expected_kind"]

        if deadline_ok and slot_ok and kind_ok:
            passed_count += 1
            category_stats[cat]["passed"] += 1
        else:
            failed_cases.append({
                "index": i + 1,
                "category": cat,
                "raw": case["raw"],
                "expected": {
                    "deadline": case["expected_deadline"],
                    "time_slot": case["expected_time_slot"],
                    "kind": case["expected_kind"],
                },
                "actual": {
                    "deadline": actual.get("deadline"),
                    "time_slot": actual.get("time_slot"),
                    "kind": actual.get("kind"),
                },
                "errors": {
                    "deadline_match": deadline_ok,
                    "slot_match": slot_ok,
                    "kind_match": kind_ok,
                }
            })

    accuracy = (passed_count / len(TEST_CASES)) * 100.0

    print("\n📈 各维度评测准确率统计:")
    print(f"{'评测维度':<22} | {'总数':<4} | {'通过':<4} | {'准确率':<8}")
    print("-" * 50)
    for cat, stat in category_stats.items():
        cat_acc = (stat["passed"] / stat["total"]) * 100.0
        print(f"{cat:<20} | {stat['total']:<4} | {stat['passed']:<4} | {cat_acc:>6.1f}%")
    print("-" * 50)
    print(f"🎯 最终全局准确率: {passed_count}/{len(TEST_CASES)} = {accuracy:.2f}%\n")

    if failed_cases:
        print(f"⚠️ 发现 {len(failed_cases)} 项未完全匹配详情:")
        for fc in failed_cases:
            print(f"  [#{fc['index']}] 文本: '{fc['raw']}' ({fc['category']})")
            print(f"       期望: {fc['expected']}")
            print(f"       实际: {fc['actual']}")
    else:
        print("🎉 恭喜！100 个用例全部通过，准确率 100.00%！")

    return {
        "total": len(TEST_CASES),
        "passed": passed_count,
        "failed": len(failed_cases),
        "accuracy": accuracy,
        "elapsed_seconds": elapsed,
        "category_stats": category_stats,
        "failed_cases": failed_cases,
        "results": results,
    }


if __name__ == "__main__":
    run_verification()
