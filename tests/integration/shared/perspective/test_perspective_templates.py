# 拆分自 test_perspective.py，覆盖：test_personal_template_config_and_task_routing, test_personal_enhancement_focus_radar, test_supervisor_slice_enhancement…

"""perspective 零 LLM 自测：偏好指令块（只调顺序与详略、不落性格原文）。

用法::

    python -m tests.test_perspective
"""

from __future__ import annotations
from domains.shared.perspective.preferences import BLOCK_TITLE, PREFERENCE_LINES, build_preference_block
from tests.support.expectations import expect
import pytest

pytestmark = pytest.mark.integration

def items_of(block: str) -> list[str]:
    return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]

def test_personal_template_config_and_task_routing() -> None:
    """测试个人模板配置与 tasks 路由：profile=user 直接走 personal_minutes，客观纪要 100% 隔离走 general_minutes。"""
    from app.config import personal_minutes_template, DEFAULT_PERSONAL_MINUTES_TEMPLATE
    from app.tasks import _template_file

    # 1. 配置测试：个人模板固定返回 personal_minutes
    expect(personal_minutes_template() == DEFAULT_PERSONAL_MINUTES_TEMPLATE, "配置：返回默认模板 personal_minutes", "")

    # 2. 路由测试：客观纪要（profile="" 或 "objective"）必须始终走 general_minutes
    obj_tpl_path = _template_file("meeting", "minutes", "", profile_value="")
    obj_content = obj_tpl_path.read_text(encoding="utf-8") if obj_tpl_path else ""
    expect("全文摘要" in obj_content and ("会议概况" not in obj_content and "本场概况与承接目标" not in obj_content and "本场概况与本人定调" not in obj_content), "路由：客观模式（profile为空）100% 保持 general_minutes", obj_content[:60])

    obj_explicit_path = _template_file("meeting", "minutes", "", profile_value="objective")
    obj_exp_content = obj_explicit_path.read_text(encoding="utf-8") if obj_explicit_path else ""
    expect("全文摘要" in obj_exp_content and ("会议概况" not in obj_exp_content and "本场概况与承接目标" not in obj_exp_content and "本场概况与本人定调" not in obj_exp_content), "路由：客观模式（profile=objective）100% 保持 general_minutes", obj_exp_content[:60])

    # 3. 路由测试：个人模式（profile="user"）默认直接走 personal_minutes
    user_tpl_path = _template_file("meeting", "minutes", "", profile_value="user")
    user_content = user_tpl_path.read_text(encoding="utf-8") if user_tpl_path else ""
    expect(("会议概况" in user_content or "本场概况与承接目标" in user_content or "本场概况与本人定调" in user_content) and ("相关行动" in user_content or "行动项与协同依赖" in user_content), "路由：个人模式（profile=user）默认走 personal_minutes", user_content[:60])

    # 4. 路由测试：个人模式不再走历史通用模板剪裁模式，即使用户/老入参传 general_minutes 也直接走 personal_minutes
    explicit_gen_path = _template_file("meeting", "minutes", "general_minutes", profile_value="user")
    explicit_gen_content = explicit_gen_path.read_text(encoding="utf-8") if explicit_gen_path else ""
    expect(("会议概况" in explicit_gen_content or "本场概况与承接目标" in explicit_gen_content or "本场概况与本人定调" in explicit_gen_content) and ("相关行动" in explicit_gen_content or "行动项与协同依赖" in explicit_gen_content), "路由：个人模式传 general_minutes 不再走剪裁，直接走 personal_minutes", explicit_gen_content[:60])

    # 5. 路由测试：个人模式显式指定其他具体场景模板（如 project_progress）时，尊重该具体模板
    explicit_proj_path = _template_file("meeting", "minutes", "project_progress", profile_value="user")
    explicit_proj_content = explicit_proj_path.read_text(encoding="utf-8") if explicit_proj_path else ""
    expect("项目概况" in explicit_proj_content or "进度追踪" in explicit_proj_content or "项目全称与背景" in explicit_proj_content, "路由：个人模式指定项目进度会时尊重具体场景模板", explicit_proj_content[:60])


def test_personal_enhancement_focus_radar() -> None:
    """测试 6 字段驱动的个人视角增强：三维切片、素材白名单、程序合成与关注雷达。"""
    from domains.shared.perspective.hits import (
        build_hit_table,
        foreign_only,
        render_radar_block,
        slice_transcript_for_person,
    )
    from domains.shared.perspective.synth import skip_reason, synthesize_perspective_profile
    from core.runner.profiles import read_user_profile

    # 1. 三维白名单切片测试
    t = (
        "技术评审会\n"
        "申家坤 00:00:10\n模型推理时延需要进一步压测优化。\n"
        "徐玥 00:00:30\n风控引擎是本季度的生命线，必须保可用性。\n"
        "张工 00:01:00\n关于demo落地，测试环境预计明天下午就绪。\n"
        "李财务 00:02:00\n各位注意及时提交差旅报销单。\n"
    )
    out, stats = slice_transcript_for_person(
        t,
        ["申家坤", "家坤"],
        full_name="申家坤",
        focus_persons=["徐玥"],
        focus_things=["demo落地"],
        min_keep_chars=50,
    )
    expect("模型推理时延" in out, "三维切片：保留本人发言", out)
    expect("风控引擎是本季度的生命线" in out, "三维切片：保留关注人发言（徐玥未喊本人名字仍保留）", out)
    expect("测试环境预计明天下午就绪" in out, "三维切片：保留含关注标的的发言（张工讨论demo落地）", out)
    expect(stats["dropped"] == 1 and "报销" not in out, "三维切片：无关他人杂务被折叠（李财务报销）", out)

    # 2. 素材过滤白名单豁免测试
    addrs = ["申家坤", "家坤"]
    others = ["徐玥", "张工", "李财务"]
    p1 = "徐玥要求本周内锁定风控引擎的评测指标"
    p2 = "张工提到关于demo落地还需要进行两轮端到端压力测试"
    p3 = "李财务提醒项目组按时提报周报与报销单"
    expect(not foreign_only(p1, addrs, others, full_name="申家坤", focus_persons=["徐玥"]), "素材过滤：重点关注人定调被豁免（不被当做无关第三方剔除）", "")
    expect(not foreign_only(p2, addrs, others, full_name="申家坤", focus_things=["demo落地"]), "素材过滤：重点关注标的相关事实被豁免", "")
    expect(foreign_only(p3, addrs, others, full_name="申家坤", focus_persons=["徐玥"], focus_things=["demo落地"]), "素材过滤：无关第三方杂务正常剔除", "")

    # 3. 雷达块渲染测试
    user_demo = {
        "name": "申家坤",
        "name_aliases": ["家坤"],
        "role": "算法工程师",
        "focus_person": ["徐玥"],
        "focus_thing": ["demo落地"],
        "preferences": ["先写我负责的待办", "关键数字与口径优先保留"],
    }
    radar = render_radar_block(user_demo)
    expect("纪要视角主体：申家坤" in radar and "动宾短语省略主语" in radar, "雷达块：包含本人身份与行为规范", radar)
    expect("重点盯防人物：徐玥" in radar and "决策定调" in radar, "雷达块：包含重点盯防人物与关注要求", radar)
    expect("重点关注标的与业务实体：demo落地" in radar and "深度深潜" in radar, "雷达块：包含重点关注标的与深潜要求", radar)

    # 4. 程序合成与跳过 LLM 建模测试
    understanding_sample = {
        "speakers": [{"name": "徐玥"}, {"name": "申家坤"}],
        "action_hints": [
            {"text": "完成demo落地模型压测并出具评测报告", "owner": "申家坤", "timing": "周五前"},
            {"text": "协调风控引擎与业务流对接", "owner": "徐玥", "timing": "下周一前"},
        ],
        "decisions": ["demo落地首期采用双轨灰度策略"],
        "risks": ["风控引擎 P99 时延超标可能阻碍上线"],
        "open_questions": [],
        "topics": [{"title": "demo落地推进与技术卡点", "participants": ["申家坤", "徐玥"]}],
    }
    table = build_hit_table(user_demo, understanding_sample)
    expect(any("徐玥" in s for s in table.focus_person_statements), "命中表：收录关注人声明与事实", str(table.focus_person_statements))
    expect(any("demo落地" in m for m in table.focus_thing_mentions), "命中表：收录关注标的提及", str(table.focus_thing_mentions))

    reason = skip_reason(user_demo, table, ["minutes"])
    expect(reason == "程序合成(关注雷达)", "跳过判定：有 focus_person/focus_thing 时程序合成接管（跳过 LLM）", str(reason))

    synth = synthesize_perspective_profile(user_demo, table)
    expect(any("demo落地" in p for p in synth["attention_points"]), "程序合成：attention_points 包含关注雷达要点", str(synth["attention_points"]))

    # 5. 读取 data/1/user.json 真实文件端到端测试
    from pathlib import Path
    from core.runner.profiles import resolve_role_template
    raw_user = read_user_profile(Path("data/1/user.json"))
    expect(raw_user is not None and raw_user.get("name") == "申家坤", "真实 user.json：读取 name 正常", str(raw_user))
    loaded_user = resolve_role_template(raw_user)
    expect(loaded_user.get("role_template") == "algorithm_engineer", "真实 user.json：role 自动映射到 role_template", str(loaded_user))
    expect(skip_reason(loaded_user, table, ["minutes"]) == "程序合成(关注雷达)", "真实 user.json：跳过建模判定生效", "")


def test_supervisor_slice_enhancement() -> None:
    """测试审核切片增强：全量放行通道、英文缩写与人名识别、优先保留个人视角硬事实。"""
    from core.runtime.supervisor_slice import (
        _is_useful_needle,
        collect_needles,
        slice_transcript,
    )

    # 1. 实体与缩写 needle 过滤器测试
    expect(_is_useful_needle("GRPO"), "needle过滤器：识别英文缩写 GRPO", "")
    expect(_is_useful_needle("ASR"), "needle过滤器：识别英文缩写 ASR", "")
    expect(_is_useful_needle("李家豪"), "needle过滤器：识别 3 字中文人名 李家豪", "")
    expect(_is_useful_needle("法本"), "needle过滤器：识别 2 字中文机构/人名 法本", "")
    expect(not _is_useful_needle("的"), "needle过滤器：过滤单字停用词", "")
    expect(not _is_useful_needle("12"), "needle过滤器：过滤短数字", "")

    # 2. 从带 markdown 格式的草稿中提取加粗实体
    draft_sample = {
        "personally_relevant_points": [
            "**李家豪**：第四批回流数据0~310min打完，现在打30~60min",
            "GRPO改动主要是奖励函数，一个是ASR的、一个是重复惩罚的",
        ]
    }
    extracted = collect_needles(draft_sample)
    expect("李家豪" in extracted, "草稿提炼：从加粗语法中提取独立实体 李家豪", str(extracted))
    expect(any("GRPO" in item for item in extracted), "草稿提炼：提取硬核技术句式", str(extracted))

    # 3. 3 万字以内常规会议全量放行通道测试
    short_text = "这是一场关于ASR和GRPO模型优化的会议，李家豪和申家坤参加了讨论。" * 200  # 约 7000 字
    excerpt, hits, used = slice_transcript(short_text, ["GRPO", "李家豪"])
    expect(used == len(short_text) and excerpt == short_text, "审核通道：3万字以内直接提供完整原文", f"used={used}, total={len(short_text)}")

    # 4. 超长会议（> 3万字）个人关注点提权与后半段采样测试
    long_prefix = "前序各部门无关业务汇报铺陈与宏观介绍。" * 1500  # 约 33000 字
    personal_tail = "申家坤和郭慧敏深入讨论了GRPO奖励函数的改动，盛晋珲拍板由李家豪跟进数据回流。"
    huge_text = f"{long_prefix}\n{personal_tail}"
    excerpt_long, hits_long, used_long = slice_transcript(
        huge_text,
        needles=["宏观介绍", "业务汇报"],
        priority_needles=["GRPO", "李家豪"],
        full_limit=30000,
    )
    expect("GRPO" in excerpt_long, "超长会议切片：后半段个人优先项 GRPO 100% 成功保留", excerpt_long[-500:])
    expect("李家豪" in excerpt_long, "超长会议切片：后半段个人优先项 李家豪 100% 成功保留", excerpt_long[-500:])

    # 5. 草稿送审保真测试（无假截断与无省略）
    from core.runtime.supervisor_slice import compact_draft_for_review
    long_desc = "长文本性能结论：本次针对小艺慧记长文本进行了大规模并发压测，实测在 60000 多字输入下系统运行还行，但达到 8~9 万字时出现性能瓶颈，修改相关配置后 token 处理速度变慢，prefill 耗费较多时间，目前手头测到的最大耗时达到 40 多秒，后续需针对超长上下文进行专项工程优化。" * 2
    full_draft = {
        "executive_summary": [long_desc],
        "personally_relevant_points": [f"个人行动项与分工事项_{i}" for i in range(25)],
    }
    compacted = compact_draft_for_review(full_draft)
    expect("...（共" not in compacted["executive_summary"][0] and len(compacted["executive_summary"][0]) == len(long_desc), "草稿送审保真：200字以上成段陈述不被假截断", str(compacted["executive_summary"][0]))
    expect(len(compacted["personally_relevant_points"]) == 25 and not any("省略" in x for x in compacted["personally_relevant_points"]), "草稿送审保真：20条以上个人事项不被中间省略", str(compacted["personally_relevant_points"]))
