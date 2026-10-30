"""200 个真实高难度待办 DDL 综合自动化测试与准确率评测脚本。

覆盖 10 大核心维度（每维度 20 例，共 200 例）：
1. 基础自然日相对偏移 (20例)
2. 周历与星期几偏移 (20例)
3. 相对整周偏移 (20例)
4. 周末语义与推断 (20例)
5. 工作日计算与跳过周末 (20例)
6. 月度边界与日期定位 (20例)
7. 季度与年份边界 (20例)
8. 具体点钟与时间顺延 (20例)
9. 业务模糊时段与复合组合 (20例)
10. 会前会后、午夜与否定表达 (20例)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from agent import run_deadline_agent_sync
from fast_path import try_fast_extract

MEETING_TIME = "2026-10-29 14:30:45"  # 周四, 2026年Q4

TEST_CASES_200: List[Dict[str, Any]] = [
    # ── Category 1: 基础自然日相对偏移 (20) ──────────────────────────
    {"category": "基础自然日相对偏移", "raw": "今天", "expected_deadline": "2026/10/29", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "明天", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "后天", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "大后天", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "昨天", "expected_deadline": "2026/10/28", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "前天", "expected_deadline": "2026/10/27", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "次日", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "1天后", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "2天后", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "3天后", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "4天后", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "5天后", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "6天后", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "7天后", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "10天后", "expected_deadline": "2026/11/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "15天后", "expected_deadline": "2026/11/13", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "30天后", "expected_deadline": "2026/11/28", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "5天内", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "3天内", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "基础自然日相对偏移", "raw": "7天内", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 2: 周历与星期几偏移 (20) ──────────────────────────
    {"category": "周历与星期几偏移", "raw": "本周一", "expected_deadline": "2026/10/26", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "本周二", "expected_deadline": "2026/10/27", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "本周三", "expected_deadline": "2026/10/28", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "本周四", "expected_deadline": "2026/10/29", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "本周五", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "周一", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "周二", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "周三", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "周四", "expected_deadline": "2026/10/29", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "周五", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "下周一", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "下周二", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "下周三", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "下周四", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "下周五", "expected_deadline": "2026/11/06", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "大下周一", "expected_deadline": "2026/11/09", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "大下周五", "expected_deadline": "2026/11/13", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "上周一", "expected_deadline": "2026/10/19", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "上周三", "expected_deadline": "2026/10/21", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历与星期几偏移", "raw": "上周五", "expected_deadline": "2026/10/23", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 3: 相对整周偏移 (20) ──────────────────────────
    {"category": "相对整周偏移", "raw": "一周后", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "两周后", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "2周后", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "三周后", "expected_deadline": "2026/11/19", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "3周后", "expected_deadline": "2026/11/19", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "四周后", "expected_deadline": "2026/11/26", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "4周后", "expected_deadline": "2026/11/26", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "一周内", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "两周内", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "三周内", "expected_deadline": "2026/11/19", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "四周内", "expected_deadline": "2026/11/26", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "一周前", "expected_deadline": "2026/10/22", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "两周前", "expected_deadline": "2026/10/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "三周前", "expected_deadline": "2026/10/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "1周后", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "2周内", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "3周内", "expected_deadline": "2026/11/19", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "4周内", "expected_deadline": "2026/11/26", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "5周后", "expected_deadline": "2026/12/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "相对整周偏移", "raw": "6周后", "expected_deadline": "2026/12/10", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 4: 周末语义与推断 (20) ──────────────────────────
    {"category": "周末语义与推断", "raw": "本周末", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "这周末", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "周末", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "下周末", "expected_deadline": "2026/11/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "大下周末", "expected_deadline": "2026/11/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "上周末", "expected_deadline": "2026/10/25", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "周六", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "周日", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "周天", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "本周六", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "本周日", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "这周六", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "这周日", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "下周六", "expected_deadline": "2026/11/07", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "下周日", "expected_deadline": "2026/11/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "下下周六", "expected_deadline": "2026/11/14", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "下下周日", "expected_deadline": "2026/11/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "大下周六", "expected_deadline": "2026/11/14", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "上周六", "expected_deadline": "2026/10/24", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末语义与推断", "raw": "上周日", "expected_deadline": "2026/10/25", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 5: 工作日计算与跳过周末 (20) ──────────────────────
    {"category": "工作日计算与跳过周末", "raw": "1个工作日后", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "一个工作日后", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "1个工作日内", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "一个工作日内", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "2个工作日后", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "两个工作日后", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "2个工作日内", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "3个工作日后", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "三个工作日后", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "3个工作日内", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "4个工作日后", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "四个工作日后", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "4个工作日内", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "5个工作日后", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "五个工作日后", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "5个工作日内", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "6个工作日后", "expected_deadline": "2026/11/06", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "7个工作日后", "expected_deadline": "2026/11/09", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "8个工作日后", "expected_deadline": "2026/11/10", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日计算与跳过周末", "raw": "10个工作日后", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 6: 月度边界与日期定位 (20) ──────────────────────
    {"category": "月度边界与日期定位", "raw": "本月底", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "月底", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "本月末", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "下月底", "expected_deadline": "2026/11/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "下月末", "expected_deadline": "2026/11/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "下月初", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "本月初", "expected_deadline": "2026/10/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "15号", "expected_deadline": "2026/11/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "20号", "expected_deadline": "2026/11/20", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "25号", "expected_deadline": "2026/11/25", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "28号", "expected_deadline": "2026/11/28", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "30号", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "本月15号", "expected_deadline": "2026/10/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "本月20号", "expected_deadline": "2026/10/20", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "下月1号", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "下月10号", "expected_deadline": "2026/11/10", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "下月15号", "expected_deadline": "2026/11/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "11月11号", "expected_deadline": "2026/11/11", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "12月12号", "expected_deadline": "2026/12/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "月度边界与日期定位", "raw": "11月1号", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 7: 季度与年份边界 (20) ──────────────────────────
    {"category": "季度与年份边界", "raw": "本季度末", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "下季度末", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "下季度初", "expected_deadline": "2027/01/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "本季度初", "expected_deadline": "2026/10/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "Q1末", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "Q2末", "expected_deadline": "2027/06/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "Q3末", "expected_deadline": "2027/09/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "Q4末", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "第一季度末", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "第二季度末", "expected_deadline": "2027/06/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "第三季度末", "expected_deadline": "2027/09/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "第四季度末", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "一季度末", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "二季度末", "expected_deadline": "2027/06/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "三季度末", "expected_deadline": "2027/09/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "四季度末", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "今年年底", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "年底", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "明年初", "expected_deadline": "2027/01/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与年份边界", "raw": "明年年底", "expected_deadline": "2027/12/31", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 8: 具体点钟与时间顺延 (20) ──────────────────────────
    {"category": "具体点钟与时间顺延", "raw": "15:30", "expected_deadline": "2026/10/29 15:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "17:00", "expected_deadline": "2026/10/29 17:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "18:30", "expected_deadline": "2026/10/29 18:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "14:45", "expected_deadline": "2026/10/29 14:45", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "3点", "expected_deadline": "2026/10/29 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "4点", "expected_deadline": "2026/10/29 16:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "5点", "expected_deadline": "2026/10/29 17:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "6点", "expected_deadline": "2026/10/29 18:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "下午3点", "expected_deadline": "2026/10/29 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "下午5点半", "expected_deadline": "2026/10/29 17:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "晚上8点", "expected_deadline": "2026/10/29 20:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "晚上9点", "expected_deadline": "2026/10/29 21:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "晚上10点", "expected_deadline": "2026/10/29 22:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "下午4点半", "expected_deadline": "2026/10/29 16:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "10:00", "expected_deadline": "2026/10/30 10:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "09:00", "expected_deadline": "2026/10/30 09:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "11:30", "expected_deadline": "2026/10/30 11:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "7点", "expected_deadline": "2026/10/30 07:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "8点", "expected_deadline": "2026/10/30 08:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "具体点钟与时间顺延", "raw": "上午10点", "expected_deadline": "2026/10/30 10:00", "expected_time_slot": None, "expected_kind": "datetime"},

    # ── Category 9: 业务模糊时段与复合组合 (20) ────────────────────
    {"category": "业务时段与复合组合", "raw": "下午", "expected_deadline": "2026/10/29", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "上午", "expected_deadline": "2026/10/30", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "中午", "expected_deadline": "2026/10/30", "expected_time_slot": "中午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "晚上", "expected_deadline": "2026/10/29", "expected_time_slot": "晚上", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "下班前", "expected_deadline": "2026/10/29", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "傍晚", "expected_deadline": "2026/10/29", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "明天上午", "expected_deadline": "2026/10/30", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "明天下午", "expected_deadline": "2026/10/30", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "明天下班前", "expected_deadline": "2026/10/30", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "今天下午", "expected_deadline": "2026/10/29", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "今天下班前", "expected_deadline": "2026/10/29", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "周五下班前", "expected_deadline": "2026/10/30", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "下周三上午", "expected_deadline": "2026/11/04", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "下周一下午", "expected_deadline": "2026/11/02", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "明早", "expected_deadline": "2026/10/30", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "明晚", "expected_deadline": "2026/10/30", "expected_time_slot": "晚上", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "今晚", "expected_deadline": "2026/10/29", "expected_time_slot": "晚上", "expected_kind": "date"},
    {"category": "业务时段与复合组合", "raw": "明天上午10点", "expected_deadline": "2026/10/30 10:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "业务时段与复合组合", "raw": "明天下午3点", "expected_deadline": "2026/10/30 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "业务时段与复合组合", "raw": "明天下午4点半", "expected_deadline": "2026/10/30 16:30", "expected_time_slot": None, "expected_kind": "datetime"},

    # ── Category 10: 会前会后、午夜与否定表达 (20) ────────────────────
    {"category": "会前会后、午夜与否定", "raw": "会后1小时", "expected_deadline": "2026/10/29 15:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "会后2小时", "expected_deadline": "2026/10/29 16:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "会后3小时", "expected_deadline": "2026/10/29 17:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "会后半小时", "expected_deadline": "2026/10/29 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "会前15分钟", "expected_deadline": "2026/10/29 14:15", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "会前30分钟", "expected_deadline": "2026/10/29 14:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "晚上12点", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "午夜", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "24点", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "零点", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会前会后、午夜与否定", "raw": "尽快完成", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "尽快", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "待定", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "未定", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "暂无", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "没提时间", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "另行通知", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "不限期", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "随缘", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "会前会后、午夜与否定", "raw": "TBD", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
]


def run_verification_200() -> Dict[str, Any]:
    print("=" * 70)
    print("🚀 开始执行待办时间转换器 200 例工业级深度评测")
    print(f"基准会议时间: {MEETING_TIME} (周四, 2026年Q4)")
    print(f"用例总数: {len(TEST_CASES_200)} 条")
    print("=" * 70)

    texts = [case["raw"] for case in TEST_CASES_200]

    # Fast-Path 架构命中预判
    fast_hits = 0
    for idx, text in enumerate(texts):
        if try_fast_extract(idx, text) is not None:
            fast_hits += 1
    llm_pending = len(texts) - fast_hits
    print(f"📊 架构分流预判: {fast_hits}/{len(texts)} ({fast_hits/len(texts)*100:.1f}%) 命中毫秒级 Fast-Path")
    print(f"                {llm_pending}/{len(texts)} ({llm_pending/len(texts)*100:.1f}%) 降级交由 DeepSeek LLM 分析")
    print("-" * 70)

    # 批量端到端执行
    start_t = time.perf_counter()
    agent_output = run_deadline_agent_sync(
        meeting_start_time=MEETING_TIME,
        texts=texts,
    )
    elapsed = time.perf_counter() - start_t
    print(f"⏱️ 200 条待办全图端到端解析总耗时: {elapsed:.2f} 秒 (平均单条 {elapsed/len(texts)*1000:.2f} 毫秒)")
    print("-" * 70)

    results = agent_output.get("results") or []
    if len(results) != len(TEST_CASES_200):
        print(f"❌ 严重错误: 输出数量 ({len(results)}) 与输入数量 ({len(TEST_CASES_200)}) 不一致！")
        return {"total": len(TEST_CASES_200), "passed": 0, "accuracy": 0.0}

    passed_count = 0
    failed_cases: List[Dict[str, Any]] = []
    category_stats: Dict[str, Dict[str, int]] = {}

    for i, case in enumerate(TEST_CASES_200):
        actual = results[i]
        cat = case["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0}
        category_stats[cat]["total"] += 1

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
            })

    accuracy = (passed_count / len(TEST_CASES_200)) * 100.0

    print("\n📈 200 例各维度评测准确率统计:")
    print(f"{'评测维度':<24} | {'总数':<4} | {'通过':<4} | {'准确率':<8}")
    print("-" * 55)
    for cat, stat in category_stats.items():
        cat_acc = (stat["passed"] / stat["total"]) * 100.0
        print(f"{cat:<22} | {stat['total']:<4} | {stat['passed']:<4} | {cat_acc:>6.1f}%")
    print("-" * 55)
    print(f"🎯 最终全局准确率: {passed_count}/{len(TEST_CASES_200)} = {accuracy:.2f}%\n")

    if failed_cases:
        print(f"⚠️ 发现 {len(failed_cases)} 项未完全匹配详情:")
        for fc in failed_cases:
            print(f"  [#{fc['index']}] 文本: '{fc['raw']}' ({fc['category']})")
            print(f"       期望: {fc['expected']}")
            print(f"       实际: {fc['actual']}")
    else:
        print("🎉 恭喜！200 个用例全部通过，准确率 100.00%！")

    return {
        "total": len(TEST_CASES_200),
        "passed": passed_count,
        "failed": len(failed_cases),
        "accuracy": accuracy,
        "elapsed_seconds": elapsed,
        "category_stats": category_stats,
        "failed_cases": failed_cases,
    }


if __name__ == "__main__":
    run_verification_200()
