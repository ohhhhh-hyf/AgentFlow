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
from tasks.minutes.agenda.alignment import group_transcript_blocks


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

