"""第二轮 200 个真实高难度待办 DDL 综合自动化测试与准确率评测脚本。

本轮特色：
- 全部采用带真实职场待办任务的完整自然语言长句（非孤立时间词）；
- 覆盖跨周跨月相对天数、工作日、周末、业务时段、精准时钟、会前会后、午夜封板；
- 包含周期任务（每周/每月）、区间任务（周一至周三）以及不确定词（或者/左右/大概/看情况）的安全消歧兜底。

10 大评测维度（每维度 20 例，共 200 例）：
1. 真实待办中的自然日相对偏移 (20例)
2. 真实待办中的周历与星期几 (20例)
3. 真实待办中的工作日流转 (20例)
4. 真实待办中的周末排期调度 (20例)
5. 真实待办中的固定月份与特定日期 (20例)
6. 真实待办中的季度与财年里程碑 (20例)
7. 真实待办中的明确钟点时间点 (20例)
8. 真实待办中的复合时段任务 (20例)
9. 真实待办中的会议锚点与午夜跨天 (20例)
10. 业务不确定性、周期与待定兜底 (20例)
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

TEST_CASES_ROUND2: List[Dict[str, Any]] = [
    # ── Category 1: 真实待办中的自然日相对偏移 (20) ──────────────────
    {"category": "自然日带上下文待办", "raw": "明天提交周报", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "后天安排客户拜访", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "大后天交付初稿", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "今天必须完成签约", "expected_deadline": "2026/10/29", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "次日汇总各部门数据", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "3天后复盘项目进度", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "4天后提交测试报告", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "5天后提交采购审批", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "6天后组织技术评审", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "7天后召开项目例会", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "8天后上线生产环境", "expected_deadline": "2026/11/06", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "9天后交付设计物料", "expected_deadline": "2026/11/07", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "10天后核算成本", "expected_deadline": "2026/11/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "12天后跟进合同走签", "expected_deadline": "2026/11/10", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "14天后提交阶段验收", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "15天后归档所有资料", "expected_deadline": "2026/11/13", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "20天后准备结项汇报", "expected_deadline": "2026/11/18", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "30天后跟进售后满意度", "expected_deadline": "2026/11/28", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "昨天已发邮件通知", "expected_deadline": "2026/10/28", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "自然日带上下文待办", "raw": "前天安排的问卷调研", "expected_deadline": "2026/10/27", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 2: 真实待办中的周历与星期几 (20) ────────────────────
    {"category": "周历带上下文待办", "raw": "下周一提交PRD文档", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "下周二组织产品宣讲", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "下周三开发准时提测", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "下周四预发布验收", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "下周五全员正式发版", "expected_deadline": "2026/11/06", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "本周五提交进项发票", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "本周一已下发通知", "expected_deadline": "2026/10/26", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "周五前完成走票流程", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "周一前把最终方案发我", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "周二提交会议纪要", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "周三安排线上答疑", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "大下周一汇报商业化方案", "expected_deadline": "2026/11/09", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "大下周五签署补充协议", "expected_deadline": "2026/11/13", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "上周一遗留的工单", "expected_deadline": "2026/10/19", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "上周三已提交退款申请", "expected_deadline": "2026/10/21", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "上周五已完成权限审批", "expected_deadline": "2026/10/23", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "下周四进行代码评审会", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "周四今日需交接完毕", "expected_deadline": "2026/10/29", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "下下周一同步海外业务进展", "expected_deadline": "2026/11/09", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周历带上下文待办", "raw": "两周后核对第一期账单", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 3: 真实待办中的工作日流转 (20) ──────────────────────
    {"category": "工作日待办流转", "raw": "1个工作日后跟进审批进度", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "2个工作日后提供修改反馈", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "3个工作日后完成资格初审", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "4个工作日后输出替代方案", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "5个工作日后答复客户诉求", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "6个工作日后交付实验样机", "expected_deadline": "2026/11/06", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "7个工作日后复核出库数据", "expected_deadline": "2026/11/09", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "8个工作日后开展全员安全培训", "expected_deadline": "2026/11/10", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "9个工作日后进行二次架构评审", "expected_deadline": "2026/11/11", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "10个工作日后出具正式评估报告", "expected_deadline": "2026/11/12", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "一个工作日后回复确认邮件", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "两个工作日后提交补正材料", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "三个工作日后给主管答复", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "四个工作日后重新评估风险", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "五个工作日后发放满意度问卷", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "工作日待办流转", "raw": "1个工作日内响应工单需求", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "range"},
    {"category": "工作日待办流转", "raw": "2个工作日内确认测试排期", "expected_deadline": "2026/11/02", "expected_time_slot": None, "expected_kind": "range"},
    {"category": "工作日待办流转", "raw": "3个工作日内提交用章申请", "expected_deadline": "2026/11/03", "expected_time_slot": None, "expected_kind": "range"},
    {"category": "工作日待办流转", "raw": "4个工作日内组织复审会", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "range"},
    {"category": "工作日待办流转", "raw": "5个工作日内办结离职流程", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "range"},

    # ── Category 4: 真实待办中的周末排期调度 (20) ────────────────────
    {"category": "周末排期调度待办", "raw": "本周末完成技术文档整理", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "这周末安排加班发版部署", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "周末把重构代码合并到主干", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "下周末前准备好培训材料", "expected_deadline": "2026/11/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "大下周末举行部门团建", "expected_deadline": "2026/11/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "周六上午技术值班", "expected_deadline": "2026/10/31", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "周日晚上系统停机维护", "expected_deadline": "2026/11/01", "expected_time_slot": "晚上", "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "本周六下午应急演练", "expected_deadline": "2026/10/31", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "本周日下班前交本周作业", "expected_deadline": "2026/11/01", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "下周六进行核心机房割接", "expected_deadline": "2026/11/07", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "下周日进行全链路容灾演练", "expected_deadline": "2026/11/08", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "这周六提交运动会报名表", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "这周日确认最终参赛名单", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "上周末已完成全库热备", "expected_deadline": "2026/10/25", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "周日提交本周工作周报总结", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "周六完成供应商数据核验", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "下周六上午做压力测试", "expected_deadline": "2026/11/07", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "下周日下午做流水对账", "expected_deadline": "2026/11/08", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "大下周六进行办公区搬迁", "expected_deadline": "2026/11/14", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "周末排期调度待办", "raw": "上周六组织消防安全检查", "expected_deadline": "2026/10/24", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 5: 真实待办中的固定月份与特定日期 (20) ──────────────
    {"category": "固定月份与日期待办", "raw": "本月底前完成财务对账", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "月底前提交电子报销单", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "本月末锁定考勤打卡数据", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月底前结算各渠道业绩", "expected_deadline": "2026/11/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月末完成全员绩效自评", "expected_deadline": "2026/11/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月初公布最终评级结果", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "本月初启动的公开招标", "expected_deadline": "2026/10/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "11月1日组织转正答辩", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "11月5号发放本月基本薪资", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "11月15号开半年度战略会", "expected_deadline": "2026/11/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "11月20号进行项目中期检查", "expected_deadline": "2026/11/20", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "12月1日启动年终考核系统", "expected_deadline": "2026/12/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "12月15号完成管理层述职", "expected_deadline": "2026/12/15", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "12月31号年度关账", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "本月30号安排大货出库", "expected_deadline": "2026/10/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "本月31号全仓盘点库存", "expected_deadline": "2026/10/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月5号提交部门年度预算", "expected_deadline": "2026/11/05", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月10号组织VIP客户沙龙", "expected_deadline": "2026/11/10", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月20号发布大版本功能", "expected_deadline": "2026/11/20", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "固定月份与日期待办", "raw": "下月25号提交自评总结表", "expected_deadline": "2026/11/25", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 6: 真实待办中的季度与财年里程碑 (20) ──────────────
    {"category": "季度与财年里程碑", "raw": "本季度末冲刺整体GMV业绩", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "下季度末完成二期工程交付", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "下季度初召开战略规划会", "expected_deadline": "2027/01/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "本季度初立项的改造项目", "expected_deadline": "2026/10/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "Q4末完成全员续签劳动合同", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "Q1末发布旗舰新品发布会", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "Q2末启动全国招商加盟", "expected_deadline": "2027/06/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "Q3末完成财年中期审计", "expected_deadline": "2027/09/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "第一季度末交付科研阶段成果", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "第二季度末完成整体验收交付", "expected_deadline": "2027/06/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "第三季度末进行全员业务总结", "expected_deadline": "2027/09/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "第四季度末做年度最终财务决算", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "一季度末完成组织架构整合", "expected_deadline": "2027/03/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "二季度末组织海外市场推介", "expected_deadline": "2027/06/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "三季度末复盘核心业务指标", "expected_deadline": "2027/09/30", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "四季度末完成全员年终考核", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "今年年底前系统整体全量上线", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "年底前举办集团年度晚会", "expected_deadline": "2026/12/31", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "明年初开展骨干岗位内部竞聘", "expected_deadline": "2027/01/01", "expected_time_slot": None, "expected_kind": "date"},
    {"category": "季度与财年里程碑", "raw": "明年年底实现全面扭亏为盈", "expected_deadline": "2027/12/31", "expected_time_slot": None, "expected_kind": "date"},

    # ── Category 7: 真实待办中的明确钟点时间点 (20) ──────────────────
    {"category": "明确点钟待办", "raw": "今天15:00准时召开线上对齐会", "expected_deadline": "2026/10/29 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "今天16:00与设计团队对齐需求", "expected_deadline": "2026/10/29 16:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "今天17:00前提交加班审批申请", "expected_deadline": "2026/10/29 17:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "今天18:00前完成移动端打卡", "expected_deadline": "2026/10/29 18:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "今天19:30参加客户答谢晚宴", "expected_deadline": "2026/10/29 19:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "今天20:00全网发布维护通告", "expected_deadline": "2026/10/29 20:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "今天21:00确认夜间压测数据", "expected_deadline": "2026/10/29 21:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天10:00参加前端候选人面试", "expected_deadline": "2026/10/30 10:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天11:00拜访核心大客户", "expected_deadline": "2026/10/30 11:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天14:00进行新产品现场演示", "expected_deadline": "2026/10/30 14:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天15:30召开各部门协同周会", "expected_deadline": "2026/10/30 15:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天16:30进行主管一对一沟通", "expected_deadline": "2026/10/30 16:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天17:30签署联合会议纪要", "expected_deadline": "2026/10/30 17:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天上午9点公司大堂准时集合", "expected_deadline": "2026/10/30 09:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天上午10点组织新员工入职培训", "expected_deadline": "2026/10/30 10:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天上午11点半团队聚餐", "expected_deadline": "2026/10/30 11:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天下午2点做技术专题分享", "expected_deadline": "2026/10/30 14:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天下午3点测试用例集中评审", "expected_deadline": "2026/10/30 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天下午4点半跟进工单处理", "expected_deadline": "2026/10/30 16:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "明确点钟待办", "raw": "明天晚上8点线上技术直播", "expected_deadline": "2026/10/30 20:00", "expected_time_slot": None, "expected_kind": "datetime"},

    # ── Category 8: 真实待办中的复合时段任务 (20) ────────────────────
    {"category": "复合时段长句待办", "raw": "明天上午按时发送工作周报", "expected_deadline": "2026/10/30", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "明天下午提交合同用章申请", "expected_deadline": "2026/10/30", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "明天下班前必须交接好所有文档", "expected_deadline": "2026/10/30", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "今天下午完成所有供应商对账", "expected_deadline": "2026/10/29", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "今天下班前发邮件确认参会名单", "expected_deadline": "2026/10/29", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "周五下班前整理好所有需求池", "expected_deadline": "2026/10/30", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周一下午召开重点项目启动会", "expected_deadline": "2026/11/02", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周二上午统一组织校招笔试", "expected_deadline": "2026/11/03", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周二下午进行技术综合面试", "expected_deadline": "2026/11/03", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周三下午评审中台架构方案", "expected_deadline": "2026/11/04", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周四上午核对税务开票数据", "expected_deadline": "2026/11/05", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周四下班前锁定本迭代发版代码", "expected_deadline": "2026/11/05", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周五上午开展全量压力测试", "expected_deadline": "2026/11/06", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周五下午做部分用户灰度发布", "expected_deadline": "2026/11/06", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "下周五下班前全员通报最终测试结果", "expected_deadline": "2026/11/06", "expected_time_slot": "下班前", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "明早汇总考勤异常说明", "expected_deadline": "2026/10/30", "expected_time_slot": "上午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "明晚提交最终版投标方案", "expected_deadline": "2026/10/30", "expected_time_slot": "晚上", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "今晚把修复代码推到测试分支", "expected_deadline": "2026/10/29", "expected_time_slot": "晚上", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "后天下午组织跨部门协同沟通会", "expected_deadline": "2026/10/31", "expected_time_slot": "下午", "expected_kind": "date"},
    {"category": "复合时段长句待办", "raw": "后天上午完成测试机房环境搭建", "expected_deadline": "2026/10/31", "expected_time_slot": "上午", "expected_kind": "date"},

    # ── Category 9: 真实待办中的会议锚点与午夜跨天 (20) ──────────────
    {"category": "会议锚点与午夜待办", "raw": "会后10分钟发送会议纪要草稿", "expected_deadline": "2026/10/29 14:40", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后15分钟上传云端录屏", "expected_deadline": "2026/10/29 14:45", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后20分钟整理白板板书", "expected_deadline": "2026/10/29 14:50", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后半小时同步领导决策结论", "expected_deadline": "2026/10/29 15:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后45分钟答复外部专家疑问", "expected_deadline": "2026/10/29 15:15", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后1小时拆解项目Action任务项", "expected_deadline": "2026/10/29 15:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后2小时发放线上调研问卷", "expected_deadline": "2026/10/29 16:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会后3小时出具正式新闻通稿", "expected_deadline": "2026/10/29 17:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会前10分钟调试好投影设备", "expected_deadline": "2026/10/29 14:20", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会前15分钟分发打印好的讲义", "expected_deadline": "2026/10/29 14:15", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会前20分钟检查扩音麦克风", "expected_deadline": "2026/10/29 14:10", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会前半小时开始入场签到", "expected_deadline": "2026/10/29 14:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "会前1小时打印好所有评审材料", "expected_deadline": "2026/10/29 13:30", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "晚上12点前关闭线上投票通道", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "今晚12点前服务器系统停机维护", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "明晚12点前截止问卷填写提交", "expected_deadline": "2026/10/31 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "今晚24点停服更新数据库", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "明天24点结束公示期", "expected_deadline": "2026/10/31 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "明天晚上12点封板代码分支", "expected_deadline": "2026/10/31 00:00", "expected_time_slot": None, "expected_kind": "datetime"},
    {"category": "会议锚点与午夜待办", "raw": "今天24点截止报名通道", "expected_deadline": "2026/10/30 00:00", "expected_time_slot": None, "expected_kind": "datetime"},

    # ── Category 10: 业务不确定性、周期与待定兜底 (20) ───────────────
    {"category": "不确定与周期待定兜底", "raw": "尽快推进该事项", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "具体启动时间待定", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "暂无明确项目排期", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "未提及具体截止时间", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "后续另行通知具体安排", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "本任务不限期完成", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "随缘交付成果即可", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "待领导确认具体实施时间", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "时间安排TBD", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "暂不设定截止时间要求", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "每周一进行例行沟通会", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "每月15号组织团队分享", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "每年年底统一复盘业务", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "明天或者后天给最终方案", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "下周二或者周三做线上对齐", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "大概下周五能够交付", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "下周三左右出初稿", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
    {"category": "不确定与周期待定兜底", "raw": "周五到周日进行全封闭测试", "expected_deadline": "2026/11/01", "expected_time_slot": None, "expected_kind": "range"},
    {"category": "不确定与周期待定兜底", "raw": "下周一至周三参加集中培训", "expected_deadline": "2026/11/04", "expected_time_slot": None, "expected_kind": "range"},
    {"category": "不确定与周期待定兜底", "raw": "看具体现场情况再定时间", "expected_deadline": None, "expected_time_slot": None, "expected_kind": "none"},
]


def run_verification_round2() -> Dict[str, Any]:
    print("=" * 70)
    print("🚀 开始执行待办时间转换器 第二轮 200 例真实待办长句评测")
    print(f"基准会议时间: {MEETING_TIME} (周四, 2026年Q4)")
    print(f"用例总数: {len(TEST_CASES_ROUND2)} 条")
    print("=" * 70)

    texts = [case["raw"] for case in TEST_CASES_ROUND2]

    # Fast-Path 架构分流预判
    fast_hits = 0
    for idx, text in enumerate(texts):
        if try_fast_extract(idx, text) is not None:
            fast_hits += 1
    llm_pending = len(texts) - fast_hits
    print(f"📊 架构分流预判: {fast_hits}/{len(texts)} ({fast_hits/len(texts)*100:.1f}%) 命中毫秒级 Fast-Path")
    print(f"                {llm_pending}/{len(texts)} ({llm_pending/len(texts)*100:.1f}%) 降级交由 DeepSeek LLM 分析")
    print("-" * 70)

    start_t = time.perf_counter()
    agent_output = run_deadline_agent_sync(
        meeting_start_time=MEETING_TIME,
        texts=texts,
    )
    elapsed = time.perf_counter() - start_t
    print(f"⏱️ 200 条长句待办全图端到端解析总耗时: {elapsed:.2f} 秒 (平均单条 {elapsed/len(texts)*1000:.2f} 毫秒)")
    print("-" * 70)

    results = agent_output.get("results") or []
    if len(results) != len(TEST_CASES_ROUND2):
        print(f"❌ 严重错误: 输出数量 ({len(results)}) 与输入数量 ({len(TEST_CASES_ROUND2)}) 不一致！")
        return {"total": len(TEST_CASES_ROUND2), "passed": 0, "accuracy": 0.0}

    passed_count = 0
    failed_cases: List[Dict[str, Any]] = []
    category_stats: Dict[str, Dict[str, int]] = {}

    for i, case in enumerate(TEST_CASES_ROUND2):
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

    accuracy = (passed_count / len(TEST_CASES_ROUND2)) * 100.0

    print("\n📈 第二轮 200 例各维度评测准确率统计:")
    print(f"{'评测维度':<24} | {'总数':<4} | {'通过':<4} | {'准确率':<8}")
    print("-" * 55)
    for cat, stat in category_stats.items():
        cat_acc = (stat["passed"] / stat["total"]) * 100.0
        print(f"{cat:<22} | {stat['total']:<4} | {stat['passed']:<4} | {cat_acc:>6.1f}%")
    print("-" * 55)
    print(f"🎯 第二轮全局准确率: {passed_count}/{len(TEST_CASES_ROUND2)} = {accuracy:.2f}%\n")

    if failed_cases:
        print(f"⚠️ 发现 {len(failed_cases)} 项未完全匹配详情:")
        for fc in failed_cases:
            print(f"  [#{fc['index']}] 文本: '{fc['raw']}' ({fc['category']})")
            print(f"       期望: {fc['expected']}")
            print(f"       实际: {fc['actual']}")
    else:
        print("🎉 恭喜！第二轮 200 个真实长句用例全部通过，准确率 100.00%！")

    return {
        "total": len(TEST_CASES_ROUND2),
        "passed": passed_count,
        "failed": len(failed_cases),
        "accuracy": accuracy,
        "elapsed_seconds": elapsed,
        "category_stats": category_stats,
        "failed_cases": failed_cases,
    }


if __name__ == "__main__":
    run_verification_round2()
