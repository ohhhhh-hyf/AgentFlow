"""actions 接口基础测试骨架 —— 待办提取。

接口：POST /api/v1/meeting/actions
用法（先启动服务，agentflow 环境）：
    python scripts/meeting/run_actions.py
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

MEETING = """• 王 00:02
好，人齐了，我们开始。今天这个会主要是把智能客服二期上线前的事情过一遍。核心就三件事：一是客户侧试用反馈下来的问题，二是技术排期和依赖，三是算法效果和验收口径。大家按自己负责的部分说，有冲突的地方当场对一下，争取今天把上线时间点定死。

• 周 00:18
那我先说客户这边。华盛那家大客户试用三周了，反馈整体能用，但有三个点比较突出。第一，转人工率偏高，他们统计大概有百分之三十几的话务最后还是落到人工，客户觉得这个数字不好看，跟我们对标过的竞品比，人家宣称百分之二十以内。第二，有些问法识别不准，他们拿了一批真实录音去试，像"我想查一下上个月的账单明细"这种带口语的句子，命中率不太行，客户原话是"感觉机器没听懂"。第三，也是最关键的一点，他们希望话术推荐这个功能月底前能上线，这个是我们商务在签约时给过承诺的，说二期一定会有，所以月底这个节点是跟客户确认过的，不是我们单方面想赶。客户那边说了，月底能上，下季度续约的事就好谈，上不了，后面评估续约的时候会比较被动。我这边能做的就是先把需求清单和验收点整理出来，另外客户答应给我们一批脱敏的真实语料，下周能到位，这对算法那边应该有用。

• 郑 00:41
那我说技术这边。话术推荐功能，底层逻辑不复杂，就是把意图识别结果加上客户标签，从话术库里检索推荐话术，再走一遍权限过滤。开发量可控，但有两个依赖要提前说。第一，话术库现在挂在第三方知识库服务上，那边接口上周才开放联调环境，联调进度比我们预期慢了一周，这是外部依赖，我们控制不了节奏。第二，我们的检索服务在压到并发两百的时候，P95 延迟会抖到两秒以上，这个问题之前提过，一直没排进去，如果话术推荐上线，这个接口会被每次会话都调用，延迟问题会被放大。我的建议是接口冻结时间定在二十号，二十四号开始全量回归，月底上线的话排期是够的，但前提是第三方那边不能再拖。另外新需求如果还往里面加，排期就要重新算，二十号之后冻结，只修不改。

• 陈 01:07
算法这边，先说意图识别。我们现在的模型在内部测试集上准确率八十六个点，召回八十一，对比上一个版本各涨了三个点左右，但离客户期望的"口语化问法能听懂"还有距离。周总说的那批真实录音问题，我们分析了坏例，主要两类：一类是口语省略主语，比如"上个月的账单"，模型会往"账单查询"和"账单下载"两个意图上分，置信度都不高；另一类是长文本，超过一百五十字的提问，截断之后信息丢失。这两类都需要更多标注语料来调，客户承诺的那批脱敏语料如果能下周到位，我们两周内能出一版针对性优化，但如果语料迟迟不到，效果就是现在这样，我不建议在语料不齐的情况下把上线效果吹得太满。另外算力这边，现在训练机晚上还要跟别的项目抢资源，如果要做针对性优化，最好给我们单独排一段训练窗口。

• 沈 01:29
测试这边我有几个硬性意见。第一，验收标准不能拍脑袋。转人工率这个指标，客户说百分之三十几高，那我们的验收线定多少？我建议明确写进验收文档，比如目标转人工率不高于百分之二十五，意图识别准确率不低于八十五，这两个是上线门禁，不达标就不签收，避免上线之后扯皮。第二，回归范围。这次改动会动到意图识别、知识库检索、会话主流程三个模块，我们准备了二百条回归用例，二十四号开始全量回归，大概需要两个完整工作日，这个时间得留出来，不能因为赶月底就把回归砍掉。第三，现有缺陷。目前库里还挂着十一个未关闭缺陷，其中有三个是并发场景下偶发超时，跟郑总说的检索延迟是同一个问题，这个必须在上线前处理掉，不然话术推荐一上线，会话量上来，这个问题会集中爆发。测试这边也同意二十号冻结，但二十四到二十六号这几天我这边不接受任何新需求变更，只接受修缺陷。

• 周 01:52
那我把话接一下，刚才陈总说语料的事，客户那批语料我下周一去催，争取周三前拿到，我这边能跟客户谈的弹性是，如果他们接受话术推荐先上、意图识别优化作为小版本跟进的方案，那月底承诺也可以谈成"话术推荐月底上线、识别优化十一月上旬"，这样排期压力会小一点。但需要今天定，我好去跟客户对。

• 郑 02:10
如果识别优化能挪到小版本，那月底只上话术推荐，排期就宽裕了。检索延迟的问题我这边排两个人，本周内把缓存和索引优化做完，二十号冻结前出验证结果。第三方那边我再去催，不行就上降级方案，检索失败时走本地缓存兜底，保证话术推荐接口稳定。

• 陈 02:27
那我可以调整一下优先级。话术推荐依赖的意图结果，用当前模型就够了，优化放到小版本，这样语料到位时间的影响就没那么大了。但我要说清楚，小版本如果也要承诺"听懂口语化问法"，那批语料和训练窗口缺一不可，到时候别拿现在的效果当最终结果对外说。

• 沈 02:43
那就按两阶段来，月底上话术推荐，验收按我提的两条门禁加话术推荐的召回率指标；识别优化小版本单独走一轮回归，不跟月底这次混。我这边回头把验收文档更新一版发出来，大家确认。

• 王 03:02
好，今天就把时间点定死。话术推荐月底上线，接口二十号冻结，二十四到二十六回归；识别优化挪到小版本，十一月上旬，具体日期等语料到位后算法给评估。周总负责催语料和跟客户对"两阶段"的口径，明天给结果。郑总负责检索优化和第三方降级方案，二十号前验证。陈总把语料标注和训练窗口的需求整理成清单，周五前给我。沈总更新验收文档，明天下班前发出来。有异议现在提，没有就按这个执行。"""


def main() -> None:
    """调用接口，解析返回 data 并按 Markdown 展示。"""
    resp = requests.post(
        f"{BASE}/api/v1/meeting/actions",
        headers={"X-User-Id": USER, "X-Request-Id": REQUEST_ID},
        json={
            "domain": "meeting",
            "task": "actions",
            "texts": {"transcript": MEETING},
            "docs": [],
            "extra": {
                "template": "",  # 空=不套模板；可填 29 个值
                "profile": "",   # 空=客观全员；可填 developer 等 7 个值
                "project": "",
                "subject": "",
                "style": "",     # 仅 minutes_styles 用
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
