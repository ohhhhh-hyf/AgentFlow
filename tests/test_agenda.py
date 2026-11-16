"""阶段三议程解析与对齐纯算法自测 (零旧代码依赖)."""
import sys
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from tasks.minutes.agenda import (
    clean_presenter_names,
    parse_agenda_text,
    ensure_agenda_plan,
    process_agenda_for_minutes,
    probe_valid_agendas,
)
from tasks.minutes.agenda.alignment import (
    group_transcript_blocks,
    _parse_timestamp_seconds,
    _TRANSITION_ROADSIGN_PATTERN,
    _BACKWARD_ROADSIGN_PATTERN,
    _TRANSITION_ROADSIGN_PATTERN_EN,
    _BACKWARD_ROADSIGN_PATTERN_EN,
)


def test_clean_presenter_names():
    """测试汇报人人名清洗 (工号、前缀、空格拆分)."""
    raw1 = "汇报人: 张三 00585440"
    assert clean_presenter_names(raw1) == ["张三"]

    raw2 = "李四 00939670; 王五"
    assert clean_presenter_names(raw2) == ["李四", "王五"]

    raw3 = "Presenter: Alice Chen"
    assert clean_presenter_names(raw3) == ["Alice Chen"]


def test_parse_markdown_table_agenda():
    """测试 Markdown 管道表格解析."""
    table = """
| 序号 | 议题全称 | 汇报人 | 时长 |
| --- | --- | --- | --- |
| 1 | 核心交易链路重构方案 | 张三 008899 | 30min |
| 2 | 跨机房容灾部署规划 | 李四 | 20min |
    """.strip()

    plan = parse_agenda_text(table)
    assert len(plan.items) == 2
    assert plan.items[0].seq == "01"
    assert plan.items[0].title == "核心交易链路重构方案"
    assert plan.items[0].presenters == ["张三"]
    assert plan.items[1].seq == "02"
    assert plan.items[1].title == "跨机房容灾部署规划"
    assert plan.items[1].presenters == ["李四"]


def test_parse_list_agenda():
    """测试列表格式议程解析."""
    text_list = """
1. 用户增长策略与渠道分析 汇报人：王海
2. 运营成本精细化管控 汇报人：刘芳 001234
    """.strip()

    plan = parse_agenda_text(text_list)
    assert len(plan.items) == 2
    assert plan.items[0].title == "用户增长策略与渠道分析"
    assert plan.items[0].presenters == ["王海"]
    assert plan.items[1].title == "运营成本精细化管控"
    assert plan.items[1].presenters == ["刘芳"]


def test_ensure_agenda_plan_from_vlm_dict():
    """测试从 VLM 视觉返回的字典格式解析."""
    vlm_dict = {
        "theme": "2026架构研讨会",
        "attendees": ["张三", "李四"],
        "agenda_items": [
            {"seq": "01", "title": "微服务治理演进", "presenters": ["赵工"]},
            {"seq": "02", "title": "茶歇合影留念", "presenters": []},
        ],
    }
    plan = ensure_agenda_plan(vlm_dict)
    assert plan.meta.theme == "2026架构研讨会"
    assert len(plan.items) == 2
    assert plan.items[0].title == "微服务治理演进"


def test_agenda_alignment_and_ceremonial_filtering():
    """测试真实文本对齐与仪式性环节过滤."""
    agenda_table = """
| 序号 | 议题名称 | 汇报人 |
| --- | --- | --- |
| 1 | 核心交易链路重构方案 | 张三 |
| 2 | 合影留念 | |
| 3 | 跨机房容灾部署规划 | 李四 |
    """.strip()

    transcript = """
主持人 09:00:00
大家早上好，欢迎参加本次架构评审会，今天我们有两个核心议题需要讨论。

张三 09:05:00
我来汇报一下核心交易链路重构方案。我们重构的主要目标是将延迟降低 50%，采用新的异步消息机制，预计三周内完成灰度。

主持人 09:40:00
好，辛苦张工。接下来大家合个影，大家看镜头！

李四 09:45:00
下面由我汇报跨机房容灾部署规划。我们计划在华东和华北建立双活机房，网络延迟控制在 15ms 以内，确保数据强一致性。

主持人 10:15:00
感谢李工，今天两位汇报的方案全部拍板通过，请大家按照排期推进，散会！
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_table)
    assert res.has_valid_agenda is True
    # 验证仪式项“合影留念”被过滤，只有 2 个实质议题
    assert len(res.valid_agendas) == 2
    assert res.valid_agendas[0].title == "核心交易链路重构方案"
    assert res.valid_agendas[1].title == "跨机房容灾部署规划"

    # 验证打标文本结构
    tagged = res.tagged_transcript
    assert "【现场审定的有效议题清单】" in tagged
    assert "【会议开场背景与主线脉络】" in tagged
    assert "【议题 1：核心交易链路重构方案】" in tagged
    assert "【议题 2：跨机房容灾部署规划】" in tagged
    assert "【会末收尾与全场定调】" in tagged


def test_empty_or_no_match_fallback():
    """测试无议程或未匹配时平滑降级."""
    transcript = "大家随便聊聊天气和周末去哪玩。"
    res = process_agenda_for_minutes(transcript, "")
    assert res.has_valid_agenda is False
    assert res.valid_agendas == []
    assert res.tagged_transcript == transcript

    probed = probe_valid_agendas(transcript, "")
    assert probed == []


def test_track_b_anonymous_content_alignment_speaker_log():
    """验证 Track B: 匿名说话人日志 + 无主讲人议题列表 (仿真 说话人日志.png).

    核心场景验证:
    1. 议程来自 VLM/OCR，主讲人 presenters 均为空;
    2. 实录全为匿名数字说话人 (如 发言者 1 00:00:03);
    3. 自适应识别切入 Track B (CONTENT);
    4. 通用尊称与语义路标准确捕获 何刚总致辞、互动交流、任务令签署与授予;
    5. 实质性保护生效：致辞与交流 > 120 字保留，活动开场视频 (0证据) 与 全体合影 (<120字过场) 干净剔除;
    6. 何刚总致辞 自动推导出汇报人 '何刚'。
    """
    agenda_dict = {
        "theme": "何刚总北研所交流会",
        "agenda_items": [
            {"seq": "01", "title": "活动开场视频播放", "presenter": ""},
            {"seq": "02", "title": "何刚总致辞", "presenter": ""},
            {"seq": "03", "title": "互动交流", "presenter": ""},
            {"seq": "04", "title": "任务令签署与授予", "presenter": ""},
            {"seq": "05", "title": "全体合影", "presenter": ""},
        ],
    }

    transcript = """
发言者 1 00:00:03
各位战队同事大家早上好，今天我们齐聚北研所交流会。下面首先有请何刚总上台致辞，大家掌声欢迎！

发言者 2 00:00:20
各位战队同事大家好，今天我们齐聚北研所，明确下一阶段攻坚方向。我们要扎实做好算法演进与工程交付，坚定信心！
当前模型训练与端侧落地进入了深水区，各战队要紧盯业务关键场景与技术指标，协同攻坚突破时延与能耗瓶颈，把核心技术真正转化为用户体验价值，确保下半年商用交付万无一失！

发言者 1 00:18:00
非常感谢何总的战略定调与殷切嘱托。接下来我们进入互动交流环节，现场问答与自由研讨，大家有什么具体业务或算法问题，随时提问交流。

发言者 3 00:18:30
何总好，我是端侧算法战队的。我们端侧时延这块目前面临算力受限挑战，跨团队对齐时模型量化收益不及预期，希望统筹协调底层架构资源，给算法团队更多工具链支持。

发言者 2 00:20:00
这个问题提得很好。端侧算力受限是客观规律，我们要坚持软硬协同，系统工程团队会后要拉通对齐，给出专班排期，两周内拿出第一版基准测试报告。

发言者 1 01:18:00
好的，交流告一段落。下面进行战队任务令签署与授予仪式，请各战队队长依次上台签署任务令并受领军令状！

发言者 2 01:19:00
任务令就是军令状，责任到人，白纸黑字！请大家以最高的标准要求自己，务必按期高质量达成各项战役交付目标！

发言者 1 01:21:00
感谢各位队长。会议最后是全体合影环节，请全体参会人员移步前台，大家看镜头，三、二、一，茄子！
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_dict)
    assert res.has_valid_agenda is True

    # 验证仪式项剔除与实质项保留：5 项议程保留 3 项实质研讨
    valid_titles = [a.title for a in res.valid_agendas]
    assert valid_titles == ["何刚总致辞", "互动交流", "任务令签署与授予"]

    # 验证主讲人自动推导 (何刚总致辞 -> 何刚)
    assert res.valid_agendas[0].presenters == ["何刚"]

    # 验证打标切片正文结构
    tagged = res.tagged_transcript
    assert "【议题 1：何刚总致辞】（汇报人：何刚）" in tagged
    assert "【议题 2：互动交流】" in tagged
    assert "【议题 3：任务令签署与授予】" in tagged
    assert "【现场审定的有效议题清单】" in tagged
    assert "活动开场视频播放" not in tagged
    assert "【议题 4：全体合影】" not in tagged
    assert "【议题 5：全体合影】" not in tagged


def test_group_transcript_blocks_formats():
    """测试多种转写文本格式的解析兼容性."""
    # 1. 带时间戳模式 (支持 [ts] spk, spk [ts], spk ts)
    text_ts = """
[00:00:10] 张三: 第一种格式
李四 [00:00:20]: 第二种格式
王五 00:00:30
第三种格式换行内容
    """.strip()
    blocks = group_transcript_blocks(text_ts)
    assert len(blocks) == 3
    assert blocks[0].speaker == "张三"
    assert blocks[0].timestamp == "00:00:10"
    assert blocks[1].speaker == "李四"
    assert blocks[1].timestamp == "00:00:20"
    assert blocks[2].speaker == "王五"
    assert blocks[2].timestamp == "00:00:30"

    # 2. 纯冒号 / 括号无时间戳模式
    text_colon = """
【赵六】
第四种括号格式
孙七：
第五种纯冒号格式
    """.strip()
    blocks_colon = group_transcript_blocks(text_colon)
    assert len(blocks_colon) == 2
    assert blocks_colon[0].speaker == "赵六"
    assert blocks_colon[1].speaker == "孙七"


def test_parse_timestamp_seconds():
    """测试时间戳秒数解析器."""
    assert _parse_timestamp_seconds("00:00:03") == 3.0
    assert _parse_timestamp_seconds("09:05:00") == 32700.0
    assert _parse_timestamp_seconds("[00:01:30]") == 90.0
    assert _parse_timestamp_seconds("(02:15)") == 135.0
    assert _parse_timestamp_seconds("01:23.500") == 83.5
    assert _parse_timestamp_seconds("") is None
    assert _parse_timestamp_seconds(None) is None
    assert _parse_timestamp_seconds("invalid:text") is None


def test_expanded_transition_and_backward_patterns():
    """测试扩充的口语化转场词与反向回溯路标."""
    # 中文推进转场
    assert _TRANSITION_ROADSIGN_PATTERN.search("我们来看一下这个方案")
    assert _TRANSITION_ROADSIGN_PATTERN.search("下面切到下一个议题")
    assert _TRANSITION_ROADSIGN_PATTERN.search("过一下这几个指标")
    assert _TRANSITION_ROADSIGN_PATTERN.search("下面由张工进行汇报")
    assert _TRANSITION_ROADSIGN_PATTERN.search("把麦交给李工")
    assert _TRANSITION_ROADSIGN_PATTERN.search("现在看关于风控的部分")

    # 中文反向回溯路标
    assert _BACKWARD_ROADSIGN_PATTERN.search("好，现在回到议题一")
    assert _BACKWARD_ROADSIGN_PATTERN.search("我们重新看第一个议题")
    assert _BACKWARD_ROADSIGN_PATTERN.search("倒回去确认一下")
    assert _BACKWARD_ROADSIGN_PATTERN.search("回头再对前面的方案")

    # 英文推进转场
    assert _TRANSITION_ROADSIGN_PATTERN_EN.search("let's turn to our next topic")
    assert _TRANSITION_ROADSIGN_PATTERN_EN.search("moving on to the budget plan")
    assert _TRANSITION_ROADSIGN_PATTERN_EN.search("hand over to Alice")

    # 英文反向回溯路标
    assert _BACKWARD_ROADSIGN_PATTERN_EN.search("let's circle back to item one")
    assert _BACKWARD_ROADSIGN_PATTERN_EN.search("jump to the previous topic")
    assert _BACKWARD_ROADSIGN_PATTERN_EN.search("revisit the first item")


def test_opening_announcement_guard_single_block():
    """测试开场单发言块集中宣读多项议程（报菜名）时，不提前冲刷跳过第一项实质议题."""
    agenda_dict = {
        "theme": "架构研讨与治理演进",
        "agenda_items": [
            {"seq": "01", "title": "交易链路架构演进", "presenters": []},
            {"seq": "02", "title": "跨机房容灾部署规划", "presenters": []},
            {"seq": "03", "title": "运营成本精细化管控", "presenters": []},
        ],
    }

    transcript = """
发言者 1 00:00:05
大家早上好，今天北研所有三个议题：第一项交易链路架构演进，第二项跨机房容灾部署规划，第三项运营成本精细化管控。

发言者 1 00:00:25
下面我们首先有请张工汇报交易链路架构演进方案。

发言者 2 00:00:35
各位好，我来汇报交易链路架构演进。我们重构的核心目标是将 P99 时延降低 50%，重构完成后异步队列吞吐能力提升 3 倍，预计下月启动灰度放量。

发言者 1 00:20:00
好的，交易链路部分告一段落，下面我们切到跨机房容灾部署规划。

发言者 3 00:20:20
容灾部署这块我们规划了双活集群架构，两地三中心部署，数据强一致保障。
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_dict)
    assert res.has_valid_agenda is True
    # 验证识别出的议题清单：开场报菜名并未将第3项假激活，实际进行了 01 和 02 两项
    valid_titles = [a.title for a in res.valid_agendas]
    assert valid_titles == ["交易链路架构演进", "跨机房容灾部署规划"]
    # 验证第 1 项议题完整保留且为第一个有效议题
    assert res.valid_agendas[0].seq == "01"
    assert res.valid_agendas[0].title == "交易链路架构演进"


def test_opening_announcement_guard_rapid_consecutive_blocks():
    """测试开场连续多个极短发言块宣读提纲时，当前议题因讨论不足 60 字受守卫保护不早跳."""
    agenda_dict = {
        "theme": "技术战略宣讲会",
        "agenda_items": [
            {"seq": "01", "title": "微服务治理方案", "presenters": []},
            {"seq": "02", "title": "数据合规治理专项", "presenters": []},
        ],
    }

    transcript = """
发言者 1 00:00:05
今天会议先看微服务治理方案。

发言者 1 00:00:15
接下来看数据合规治理专项。

发言者 1 00:00:25
下面请王工先开始讲微服务治理。

发言者 2 00:00:35
大家好，关于微服务治理方案，我们本期核心是做服务网格 Service Mesh 的下沉与全链路熔断治理，目前已覆盖 80% 核心集群，稳定性指标提升显著。

发言者 1 00:15:00
辛苦王工，微服务治理汇报完毕，下面我们切到数据合规治理专项。

发言者 3 00:15:20
数据合规这块，我们重点梳理了敏感字段与访问控制审计日志，全面满足监管合规要求。
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_dict)
    assert res.has_valid_agenda is True
    valid_titles = [a.title for a in res.valid_agendas]
    assert valid_titles == ["微服务治理方案", "数据合规治理专项"]
    # 验证王工的汇报正确归入第 1 个议题微服务治理
    item1_blocks = res.valid_agendas[0].matched_blocks
    assert any("Service Mesh" in b.content for b in item1_blocks)


def test_track_b_controlled_backtracking():
    """验证 Track B: 会议讨论议题 1 -> 议题 2 -> 显式回到议题 1，内容完整聚拢回前序议题."""
    agenda_dict = {
        "theme": "技术架构研讨会",
        "agenda_items": [
            {"seq": "01", "title": "微服务治理演进", "presenters": []},
            {"seq": "02", "title": "跨机房容灾部署规划", "presenters": []},
        ],
    }

    transcript = """
发言者 1 00:00:10
大家早上好，我们首先进入微服务治理演进的讨论。

发言者 2 00:00:30
我来汇报微服务治理演进。本期我们完成了网格化代理的下沉，整体调用链路时延优化了 30%，熔断策略已在生产集群全量生效。

发言者 1 00:15:00
辛苦王工。接下来我们切到跨机房容灾部署规划。

发言者 3 00:15:30
关于跨机房容灾部署规划，我们规划了双活集群架构，两地三中心部署，专线延迟压到 15ms 以内，保障核心业务故障分钟级自动切换。

发言者 1 00:30:00
好，容灾部分明确了。现在我们回到议题一（微服务治理演进），把刚才讨论的时延兜底指标再核对一下。

发言者 2 00:30:30
好的，关于微服务治理的时延兜底指标，我们补充了降级超时阈值设为 200ms 的保护规则，已与 SRE 团队完成确认。

发言者 1 00:40:00
没问题，今天的两项技术议题全部拍板通过，散会！
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_dict)
    assert res.has_valid_agenda is True
    valid_titles = [a.title for a in res.valid_agendas]
    assert valid_titles == ["微服务治理演进", "跨机房容灾部署规划"]

    # 验证议题 1 成功聚合了开场的汇报与回溯后的补充讨论
    item1 = res.valid_agendas[0]
    assert item1.title == "微服务治理演进"
    item1_contents = " ".join(b.content for b in item1.matched_blocks)
    assert "网格化代理的下沉" in item1_contents
    assert "降级超时阈值设为 200ms" in item1_contents

    # 验证打标文本结构
    tagged = res.tagged_transcript
    assert "【议题 1：微服务治理演进】" in tagged
    assert "【议题 2：跨机房容灾部署规划】" in tagged
    assert "降级超时阈值设为 200ms" in tagged


def test_track_b_grep_implicit_transition():
    """验证 Track B: 主持人未说'接下来'，发言人直接开讲下一议题时通过专名 Grep 平滑切入."""
    agenda_dict = {
        "theme": "技术战略会",
        "agenda_items": [
            {"seq": "01", "title": "交易链路重构方案", "presenters": []},
            {"seq": "02", "title": "跨机房容灾部署规划", "presenters": []},
        ],
    }

    transcript = """
发言者 1 00:00:10
我们首先看交易链路重构方案。

发言者 2 00:00:30
交易链路重构方案重点在改造异步事件队列与订单状态机，目前核心代码已交付评审，单机吞吐提升 3 倍。

发言者 3 00:18:00
跨机房容灾部署规划这块，我们两地三中心基础设施已经全部就绪，容灾演练指标正常，专线时延压到 15ms，随时可以启动联合演练。

发言者 1 00:35:00
感谢两位，方案全部通过！
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_dict)
    assert res.has_valid_agenda is True
    valid_titles = [a.title for a in res.valid_agendas]
    assert valid_titles == ["交易链路重构方案", "跨机房容灾部署规划"]

    # 验证未说转场词的发言者 3 被精准切入议题 2
    item2 = res.valid_agendas[1]
    assert item2.title == "跨机房容灾部署规划"
    assert any("两地三中心" in b.content for b in item2.matched_blocks)


def test_track_b_grep_does_not_trigger_on_casual_mention():
    """验证 Track B: 当前议题发言中偶发提及后序议题的单个泛词，不会被误切题."""
    agenda_dict = {
        "theme": "技术战略会",
        "agenda_items": [
            {"seq": "01", "title": "交易链路重构方案", "presenters": []},
            {"seq": "02", "title": "跨机房容灾部署规划", "presenters": []},
        ],
    }

    transcript = """
发言者 1 00:00:10
我们首先看交易链路重构方案。

发言者 2 00:00:30
交易链路重构方案重点在改造异步事件队列。我们在方案设计时也规划了异常情况的处理逻辑，后续跟容灾团队再对齐。我们本期主要目标是确保交易高可用。

发言者 2 00:05:00
另外交易链路的核心数据库分表分库改造也完成了第一阶段，读写性能提升明显。

发言者 1 00:20:00
辛苦张工。下面我们来看跨机房容灾部署规划。

发言者 3 00:20:30
跨机房容灾部署规划这块，我们规划了双活集群架构，两地三中心部署。
    """.strip()

    res = process_agenda_for_minutes(transcript, agenda_dict)
    assert res.has_valid_agenda is True
    # 验证发言者 2 偶发提到“规划”和“容灾”，但没有成体系密集命中，依然全部归于议题 1
    item1 = res.valid_agendas[0]
    assert len(item1.matched_blocks) >= 2
    assert any("分表分库改造" in b.content for b in item1.matched_blocks)



