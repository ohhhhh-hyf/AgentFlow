"""minutes_trace 接口基础测试骨架 —— 溯源纪要。

接口：POST /api/v1/meeting/minutes_trace
用法（先启动服务，agentflow 环境）：
    python scripts/meeting/run_minutes_trace.py
"""
# ============================================================================
# 可选字段取值（请求体 texts / extra）
# ============================================================================
# 一、texts 对象 key（4 个固定 key，值为字符串，多段用换行分隔）
#   transcript     会议转写文本（主输入）
#   teacher_focus  老师重点文本（主输入，catalog/checklist 用）
#   keypoints      用户重点文本（minutes_trace 溯源材料）
#   notes          用户笔记文本（minutes_trace 溯源材料）
#
# 二、extra.profile（7 个值；空字符串 = 客观全员）
#   ""               客观全员（默认）
#   algorithm_engineer  算法人员
#   client_manager      客户经理
#   developer           开发人员
#   product_manager     产品经理
#   project_manager     项目经理
#   tester              测试人员
#
# 三、extra.template（29 个值；空字符串 = 不套模板，用任务默认输出）
#   meeting_minutes_team_meeting              团队例会
#   meeting_minutes_project_progress          项目进度会
#   meeting_minutes_decision_review           决策评审会
#   meeting_minutes_workshop_session          工作研讨会
#   meeting_minutes_retrospective_session     总结复盘会
#   meeting_minutes_exchange_forum            沟通交流会
#   study_notes_class_transcript              课堂记录
#   study_notes_special_lecture               专题讲座
#   study_notes_group_seminar                 小组讨论
#   study_notes_knowledge_memo                知识笔记
#   study_notes_debate_forum                  辩论会
#   dialogue_interview_research_dialogue      调研访谈
#   dialogue_interview_interview_transcript   采访记录
#   job_interview_hiring_report               面试报告
#   job_interview_interview_debrief           面试复盘
#   medical_consultation_clinical_advisory    就医咨询
#   medical_consultation_psychological_session心理咨询
#   legal_consultation_legal_advisory         法律咨询
#   legal_consultation_court_transcript       庭审记录
#   legal_consultation_contract_vetting       合同审核
#   press_conference_media_briefing           新闻发布
#   press_conference_product_launch           产品发布
#   press_conference_government_bulletin      政府报告
#   press_conference_media_qa_session         媒体问答
#   daily_journal_general_minutes             通用纪要
#   daily_journal_personal_memo               个人备忘
#   daily_journal_conversation_transcript     对话记录
#   daily_journal_site_visit_tour             参观游览
#   daily_journal_home_school_liaison         家校沟通
#
# 四、extra.style（5 个值，仅 minutes_styles 生效）
#   time        时间线（叙事节奏）
#   logic       逻辑总分（归纳分类）
#   causal      因果推导（风险与动因）
#   party       主体责权（立场与博弈）
#   urgency     决策时效（执行倒计时）
# ============================================================================

import json
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.common import REQUEST_ID  # noqa: E402


BASE = "http://127.0.0.1:8000"
USER = "1"  # X-User-Id 必填

# texts 三个 type：transcript 主文本 / keypoints 用户重点 / notes 用户笔记
MEETING = """项目例会：张三汇报后端接口开发完成，李四反馈前端联调中，支付模块存在风险，
会议决定下周三上线测试环境，由王五负责协调。"""
KEYPOINTS = "关注支付模块风险与上线时间"
NOTES = "王五负责协调上线"


def main() -> None:
    """调用接口，解析返回 data 并按 Markdown 展示。"""
    resp = requests.post(
        f"{BASE}/api/v1/meeting/minutes_trace",
        headers={"X-User-Id": USER, "X-Request-Id": REQUEST_ID},
        json={
            "domain": "meeting",
            "task": "minutes_trace",
            "texts": {
                "transcript": MEETING,
                "keypoints": KEYPOINTS,
                "notes": NOTES
            },
            "docs": [],
            "extra": {
                "template": "",   # 空=不套模板
                "profile": "",    # 空=客观全员
                "project": "",    # 会议关联项目 ID
                "subject": "",
                "style": "",      # 仅 minutes_styles 用
            },
        },
        timeout=300,
    )
    data = resp.json()
    payload = data.get("data") or {}
    md_text = payload.get("text") or ""
    print(f"HTTP {resp.status_code}")
    print(f"  code: {data.get('code')}")
    print(f"  request_id: {data.get('request_id')}")
    print(f"  message: {data.get('message')}")
    monitor = data.get("monitor") or {}
    print(f"  monitor.token_usage: {monitor.get('token_usage')}")
    print(f"  monitor.cache_hit: {monitor.get('cache_hit')}")
    print(f"  monitor.cost_time: {monitor.get('cost_time')}")
    print(f"  data.file_name: {payload.get('file_name')}")
    request_id = REQUEST_ID
    out_dir = Path(__file__).resolve().parents[2] / "data" / USER / "output" / REQUEST_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "result.md"
    out_path.write_text(md_text, encoding="utf-8")
    print(f"已保存 Markdown：{out_path}")
    print("--- Markdown 内容 ---")
    print(md_text)


if __name__ == "__main__":
    main()
    print("PASS")
