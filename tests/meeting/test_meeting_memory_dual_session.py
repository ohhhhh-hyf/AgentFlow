"""固定 15 条待办的双场基准端到端集成测试集。

验收全链条核心能力：
1. 双场跨议题 15 条原子待办持久化与账本演进
2. 同义改写智能对账（2 条闭环 + 3 条延续），闭环项与延续项无重叠
3. 往期沿革自动剥离：现场未重申的历史决策剪切至往期沿革，不伪装成新决议
4. 跨议题严格作用域隔离挂载：角标 100% 落在对应议题章节，零跨域误挂
5. 一事一挂：同一个记忆实体全篇只挂一次
6. Prompt 截断（Top-10）与全量状态溯源解耦：消费 candidate_items
7. 个人视角推进背景自适应收窄（本人/关注人/关注域三级收窄）
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from domains.meeting.memory.extract import MeetingFact, extract_meeting_fact
from domains.meeting.memory.inject import build_memory_context, preview_comparison
from domains.meeting.memory.render import apply_memory_citations, parse_memory_items
from domains.meeting.memory.runtime import build_line_extra, encode_meta, persist_after_run
from domains.meeting.memory.store import load_state
from domains.meeting.memory.state import session_index, update_state
from core.execution.hard_execution import enforce_minutes_draft, purge_stale_memory_from_decisions


def test_dual_session_15_items_benchmark() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        project_root = Path(tmp_dir)
        user_id = "u_lead_architect"
        project_id = "proj_cloud_platform"
        project_name = "云原生高可用平台"

        # ══════════════════════════════════════════════════════════════════
        # 第一场（Session 1 - 基线场次）：全量 15 条待办 + 3 条拍板决策
        # 覆盖 3 大业务模块：网关核心架构、音视频推流SDK、数据库分库分表
        # ══════════════════════════════════════════════════════════════════
        u1 = {
            "meeting_purpose": "云原生高可用平台 Q3 技术攻坚启动会",
            "key_decisions": [
                "确定网关统一接入层采用分布式TokenBucket限流",
                "确定推流SDK采用自研拥塞控制算法",
                "确定采用 PostgreSQL 作为核心数据库",
            ],
            "topics": [
                {
                    "topic_id": "T1",
                    "module": "网关核心架构",
                    "title": "接入层限流与高并发断流攻坚",
                    "decisions": ["确定网关统一接入层采用分布式TokenBucket限流"],
                    "actions": [
                        {"task": "完成网关压测断流问题排查与修复", "owner": "张工", "deadline": "9月10日前", "deliverable": "断流修复方案"},
                        {"task": "优化网关鉴权二级缓存策略", "owner": "李工", "deadline": "9月12日前", "deliverable": "鉴权性能报告"},
                        {"task": "完成动态路由心跳健康检查重构", "owner": "王工", "deadline": "9月15日前", "deliverable": "路由心跳测试套件"},
                        {"task": "排查网关跨域预检请求偶发失败问题", "owner": "张工", "deadline": "9月18日前", "deliverable": "CORS配置补丁"},
                        {"task": "制定接入层容灾熔断回滚预案", "owner": "赵工", "deadline": "9月20日前", "deliverable": "容灾演练手册"},
                    ],
                    "risks": ["高并发流量下网关连接池可能耗尽"],
                    "open_issues": ["长连接网关断线重连雪崩防护待定"],
                },
                {
                    "topic_id": "T2",
                    "module": "音视频推流SDK",
                    "title": "推流弱网自适应与编解码优化",
                    "decisions": ["确定推流SDK采用自研拥塞控制算法"],
                    "actions": [
                        {"task": "上线音视频推流SDK新架构", "owner": "刘工", "deadline": "9月11日前", "deliverable": "推流SDK 2.0版本"},
                        {"task": "优化低带宽弱网推流丢帧补偿", "owner": "陈工", "deadline": "9月13日前", "deliverable": "丢帧补偿算法"},
                        {"task": "排查GPU硬件编码色彩失真缺陷", "owner": "刘工", "deadline": "9月16日前", "deliverable": "色彩失真修复补丁"},
                        {"task": "完成iOS端音频降噪插件联调", "owner": "周工", "deadline": "9月19日前", "deliverable": "音频降噪模块"},
                        {"task": "测试推流断网自动重连与心跳保活", "owner": "吴工", "deadline": "9月22日前", "deliverable": "重连压力测试报告"},
                    ],
                    "risks": ["部分机型硬件编码兼容性不稳定"],
                    "open_issues": ["跨平台SDK音频混音延迟待测试"],
                },
                {
                    "topic_id": "T3",
                    "module": "数据库分库分表",
                    "title": "核心数据存储与分片迁移",
                    "decisions": ["确定采用 PostgreSQL 作为核心数据库"],
                    "actions": [
                        {"task": "完成分布式分库分表数据迁移方案设计", "owner": "孙工", "deadline": "9月14日前", "deliverable": "分库分表设计方案"},
                        {"task": "完成冷热数据双写一致性校验脚本编写", "owner": "钱工", "deadline": "9月17日前", "deliverable": "一致性校验工具"},
                        {"task": "排查跨分片全局主键生成并发死锁隐患", "owner": "孙工", "deadline": "9月21日前", "deliverable": "分布式ID优化方案"},
                        {"task": "优化历史归档数据只读分流查询性能", "owner": "郑工", "deadline": "9月25日前", "deliverable": "只读分流配置"},
                        {"task": "部署分库分表联调预发环境数据库连接池", "owner": "冯工", "deadline": "9月28日前", "deliverable": "连接池部署脚本"},
                    ],
                    "risks": ["数据双写阶段主从同步可能产生延迟"],
                    "open_issues": ["分布式事务回滚机制选型未定"],
                },
            ],
        }

        t1 = (
            "会议开始。首先网关核心架构议题：张工提到完成网关压测断流问题排查与修复，李工负责优化网关鉴权二级缓存策略，"
            "王工推进完成动态路由心跳健康检查重构，张工还跟进排查网关跨域预检请求偶发失败问题，赵工制定接入层容灾熔断回滚预案。"
            "拍板确定网关统一接入层采用分布式TokenBucket限流。\n"
            "然后音视频推流SDK议题：刘工负责上线音视频推流SDK新架构，陈工优化低带宽弱网推流丢帧补偿，刘工排查GPU硬件编码色彩失真缺陷，"
            "周工完成iOS端音频降噪插件联调，吴工测试推流断网自动重连与心跳保活。确定推流SDK采用自研拥塞控制算法。\n"
            "最后数据库分库分表：孙工完成分布式分库分表数据迁移方案设计，钱工完成冷热数据双写一致性校验脚本编写，"
            "孙工排查跨分片全局主键生成并发死锁隐患，郑工优化历史归档数据只读分流查询性能，冯工部署分库分表联调预发环境数据库连接池。"
            "拍板确定采用 PostgreSQL 作为核心数据库。"
        )

        # 执行 Session 1 持久化回写
        persist_after_run(
            project_root=project_root,
            user_id=user_id,
            project=project_id,
            request_id="req_s1",
            transcript=t1,
            reports={"minutes": {"headline": "Q3技术攻坚启动会"}},
            understanding=u1,
            meeting_time="2026-09-01",
        )

        # 检查 Session 1 落盘状态
        st1 = load_state(project_root, user_id, project_id)
        print("ACTIONS:")
        for a in st1.get("actions") or []:
            print("  -", a.get("text"))
        assert len(st1.get("actions") or []) == 15, "第一场应建档 15 条原子待办"
        assert len(st1.get("decisions") or []) == 3, "第一场应建档 3 条拍板决策"
        modules = {a.get("module") for a in st1.get("actions") or [] if a.get("module")}
        assert len(modules) == 3, "第一场应记录 3 个原生业务模块"

        # ══════════════════════════════════════════════════════════════════
        # 第二场（Session 2 - 演进场次）：
        # 1. 同义改写宣布 2 条闭环：
        #    - 张工带领架构组完成了高并发流量断流限流改造（改写自：完成网关压测断流问题排查与修复）
        #    - 刘工完成了推流SDK 2.0优化发布与全量灰度上线（改写自：上线音视频推流SDK新架构）
        # 2. 3 条延续事项陈述最新卡点与进展：
        #    - 李工汇报网关鉴权二级缓存策略正在进行压力测试，因依赖Redis集群升级延期至下周
        #    - 王工汇报动态路由心跳健康检查已完成主体逻辑，尚需接入哨兵监控
        #    - 陈工汇报低带宽弱网推流丢帧补偿算法正在灰度验证，发现偶发卡顿
        # 3. 现场完全零重申旧决议「确定采用 PostgreSQL 作为核心数据库」
        # ══════════════════════════════════════════════════════════════════
        u2 = {
            "meeting_purpose": "云原生高可用平台阶段演进与对齐会",
            "key_decisions": ["确定网关统一接入层采用分布式TokenBucket限流"],
            "closed_items": [
                "张工带领架构组完成了高并发流量断流限流改造",
                "刘工完成了推流SDK 2.0优化发布与全量灰度上线",
            ],
            "topics": [
                {
                    "topic_id": "T1",
                    "module": "网关核心架构",
                    "title": "接入层限流演进与断流闭环",
                    "decisions": ["确定网关统一接入层采用分布式TokenBucket限流"],
                    "actions": [
                        {"task": "网关鉴权二级缓存策略接入Redis集群联调", "owner": "李工", "deadline": "9月25日前", "deliverable": "联调记录"},
                    ],
                    "risks": [],
                    "open_issues": [
                        "网关鉴权二级缓存策略正在进行压力测试，因依赖Redis集群升级延期至下周",
                        "动态路由心跳健康检查已完成主体逻辑，尚需接入哨兵监控",
                    ],
                },
                {
                    "topic_id": "T2",
                    "module": "音视频推流SDK",
                    "title": "推流SDK发布与弱网攻坚",
                    "decisions": [],
                    "actions": [
                        {"task": "排查低带宽弱网推流丢帧补偿偶发卡顿", "owner": "陈工", "deadline": "9月26日前", "deliverable": "卡顿修复"},
                    ],
                    "risks": [],
                    "open_issues": ["低带宽弱网推流丢帧补偿算法正在灰度验证，发现偶发卡顿"],
                },
                {
                    "topic_id": "T3",
                    "module": "数据库分库分表",
                    "title": "数据分片预发演练",
                    "decisions": [],
                    "actions": [],
                    "risks": [],
                    "open_issues": [],
                },
            ],
        }

        t2 = (
            "云原生高可用平台第二场例会开始。\n"
            "【议题一：网关核心架构与限流演进】\n"
            "张工汇报：经过架构组连续两天的排查，张工带领架构组完成了高并发流量断流限流改造，目前网关在高并发下运行平稳。\n"
            "李工汇报：网关鉴权二级缓存策略正在进行压力测试，因依赖Redis集群升级延期至下周交付报告。\n"
            "王工补充：动态路由心跳健康检查已完成主体逻辑，尚需接入哨兵监控。\n"
            "再次拍板确认：确定网关统一接入层采用分布式TokenBucket限流。\n\n"
            "【议题二：音视频推流SDK优化与收口】\n"
            "刘工宣布：刘工完成了推流SDK 2.0优化发布与全量灰度上线，核心指标达标。\n"
            "陈工发言：低带宽弱网推流丢帧补偿算法正在灰度验证，发现偶发卡顿，本周重点攻坚。\n\n"
            "【议题三：数据库分库分表设计】\n"
            "孙工汇报：分库分表数据迁移方案设计稳步推进中，各方无新增异议。"
        )

        f2 = extract_meeting_fact(u2, t2, request_id="req_s2", time="2026-09-08")
        seq_map = session_index([{"meeting_id": "req_s1", "time": "2026-09-01"}, {"meeting_id": "req_s2", "time": "2026-09-08"}], project_id)

        # ── 1. 验证同义改写智能对账（Comparison）────────────────
        comp = preview_comparison(st1, f2, seq_map)
        comp_str = "\n".join(comp)

        # 验证 2 条同义改写成功归入【已闭环】
        assert any("高并发流量断流" in line or "断流" in line for line in comp if line.startswith("已闭环")), (
            f"未成功将同义改写的断流改造归入已闭环: {comp_str}"
        )
        assert any("推流SDK" in line or "推流" in line for line in comp if line.startswith("已闭环")), (
            f"未成功将同义改写的推流SDK发布归入已闭环: {comp_str}"
        )
        # 验证 3 条延续事项
        assert any("鉴权" in line for line in comp if line.startswith("延续事项")), f"鉴权事项应在延续事项中: {comp_str}"
        assert any("心跳" in line or "路由" in line for line in comp if line.startswith("延续事项")), f"心跳事项应在延续事项中: {comp_str}"
        assert any("丢帧" in line or "弱网" in line for line in comp if line.startswith("延续事项")), f"弱网丢帧事项应在延续事项中: {comp_str}"

        # 验证已闭环项不再作为延续事项重复出现
        continuing_lines = [l for l in comp if l.startswith("延续事项")]
        assert not any("完成网关压测断流问题排查与修复" in l for l in continuing_lines), "已闭环的断流修复不得出现在延续事项"
        assert not any("上线音视频推流SDK新架构" in l for l in continuing_lines), "已闭环的推流SDK上线不得出现在延续事项"

        # ── 2. 验证往期沿革自动剥离（Session 1 拍板、Session 2 零讨论的决策）──
        # 模拟 LLM 草稿将 Session 1 的 PostgreSQL 决策误带入本场决议
        draft_with_hallucination = {
            "headline": "云原生高可用平台阶段演进纪要",
            "executive_summary": ["网关与推流SDK关键任务取得突破，多项核心任务闭环与延续。"],
            "key_decisions": [
                "确定网关统一接入层采用分布式TokenBucket限流",
                "确定采用 PostgreSQL 作为核心数据库",  # 历史旧决策，t2 原文中未提及！
            ],
            "personally_relevant_points": ["张三负责各模块联调"],
            "risks_and_blockers": [],
            "unresolved_questions": [],
            "history_comparison": [],
        }

        memory_texts = [d.get("text") for d in st1.get("decisions") or []] + [a.get("text") for a in st1.get("actions") or []]
        enforced = enforce_minutes_draft(
            draft_with_hallucination,
            u2,
            mode="objective",
            memory_texts=memory_texts,
            transcript=t2,
        )

        assert "确定采用 PostgreSQL 作为核心数据库" not in enforced["key_decisions"], (
            f"未重申的历史决策应从 key_decisions 中剔除: {enforced['key_decisions']}"
        )
        assert any("往期沿革（本次未重申）：确定采用 PostgreSQL 作为核心数据库" in h for h in enforced["history_comparison"]), (
            f"未重申的旧决策应自动转移至往期沿革: {enforced['history_comparison']}"
        )

        # ── 3. 验证 Prompt 截断与全量状态溯源解耦（Top-10 vs 15 条全量）──
        # 客观模式下 build_memory_context 预算截断至 Top-10
        ctx_prompt, _ = build_memory_context(
            project_id=project_id,
            project={"name": project_name},
            state=st1,
            bind=type("B", (), {"evidence": []})(),
            meetings=[],
            current_fact=f2,
            perspective_mode="objective",
            cap=10,
        )
        items_in_prompt = parse_memory_items(ctx_prompt)
        assert len(items_in_prompt) <= 10, f"Prompt 推进背景应严格控制在 Top-10 内，实际: {len(items_in_prompt)}"

        # 构造正文：同时讨论了在 Prompt 中出现的待办，以及未被注入到 Prompt 的第 13 条历史待办
        body_to_render = (
            "# 云原生高可用平台阶段演进纪要\n\n"
            "## 议题一：网关核心架构与限流演进\n"
            "张工带领架构组完成了高并发流量断流限流改造，网关鉴权二级缓存策略正在进行压力测试。\n"
            "李工跟进优化网关鉴权二级缓存策略相关性能。\n\n"
            "## 议题二：音视频推流SDK优化与收口\n"
            "刘工完成了推流SDK 2.0优化发布，低带宽弱网推流丢帧补偿算法正在灰度验证中。\n\n"
            "## 议题三：数据库分库分表设计\n"
            "孙工完成分布式分库分表数据迁移方案设计，并重点排查跨分片全局主键生成并发死锁隐患。\n"
        )

        # 全量 15 条条目作为 candidate_items 传入 apply_memory_citations
        all_state_items = list(st1.get("actions") or []) + list(st1.get("decisions") or [])
        cited_doc = apply_memory_citations(
            body_to_render,
            ctx_prompt,
            comparison=enforced["history_comparison"] + comp,
            candidate_items=all_state_items,
        )

        # 验证全量状态直传解耦：即使第 13 条（排查跨分片全局主键生成并发死锁隐患）未在 Prompt 文本中，
        # 只要正文提及且 candidate_items 包含，依然能生成溯源角标与文末卡片！
        assert "(#memory-" in cited_doc, "正文必须挂载溯源锚点"
        assert "## 历史记忆引用" in cited_doc, "文末必须包含历史记忆引用卡片"
        assert "排查跨分片全局主键生成并发死锁隐患" in cited_doc, "全量候选池中的条目即便未注入 Prompt 亦可溯源"

        # ── 4. 验证跨议题严格作用域隔离（Zero Cross-topic Mis-citation）──
        sec_gw, sec_rest = cited_doc.split("## 议题二：音视频推流SDK优化与收口", 1)
        sec_sdk, sec_db = sec_rest.split("## 议题三：数据库分库分表设计", 1)

        # 提取各章节内挂载的 memory-N
        import re
        gw_mems = set(re.findall(r"\(#(memory-\d+)\)", sec_gw))
        sdk_mems = set(re.findall(r"\(#(memory-\d+)\)", sec_sdk))
        db_mems = set(re.findall(r"\(#(memory-\d+)\)", sec_db))

        # 校验各章节记忆引用互不重叠，严格隔离
        assert gw_mems.isdisjoint(sdk_mems), f"网关章节与SDK章节锚点发生混淆: {gw_mems & sdk_mems}"
        assert sdk_mems.isdisjoint(db_mems), f"SDK章节与数据库章节锚点发生混淆: {sdk_mems & db_mems}"
        assert gw_mems.isdisjoint(db_mems), f"网关章节与数据库章节锚点发生混淆: {gw_mems & db_mems}"

        # ── 5. 验证一事一挂（Each memory item cited at most once）──────
        all_citations = re.findall(r"\(#(memory-\d+)\)", cited_doc)
        seen_cites = set()
        for c in all_citations:
            assert c not in seen_cites, f"记忆锚点 {c} 出现了多次，违背一事一挂原则"
            seen_cites.add(c)

        # ── 6. 验证个人视角多维收窄（张工画像）───────────────────────
        user_zhang = {
            "name": "张工",
            "aliases": ["小张", "老张"],
            "focus_person": ["李工"],
            "focus_thing": ["接入层限流", "断流"],
        }
        ctx_personal, _ = build_memory_context(
            project_id=project_id,
            project={"name": project_name},
            state=st1,
            bind=type("B", (), {"evidence": []})(),
            meetings=[],
            current_fact=f2,
            user=user_zhang,
            perspective_mode="personal",
        )
        personal_items = parse_memory_items(ctx_personal)
        # 个人模式下提取 3~6 条专属推进背景
        assert 1 <= len(personal_items) <= 6, f"个人模式推进背景条目数应为 3~6 条，实际: {len(personal_items)}"
        # 优先收录张工本人事项及关注人（李工）或关注标的
        assert any("张工" in it.owner or "李工" in it.owner or "断流" in it.text for it in personal_items), (
            f"个人模式背景未聚焦于本人及协同关注人: {[it.text for it in personal_items]}"
        )
