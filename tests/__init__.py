"""AgentFlow 自动化测试体系。

目录结构与职责划分：
--------------------
- ``tests/core/``：编排内核、执行门禁、模板路由、视角建模与监督优化测试
  - ``test_core.py``：契约 DSL、模型校验不变量、画像选档与角色合并测试
  - ``test_engine_smoke.py``：LangGraph DAG 拓扑构建与纯 TaskEvent 事件流调度冒烟测试
  - ``test_template_router.py``：32 垂直场景模板自动判型、占位符清洗、字数预算与门禁校验
  - ``test_perspective.py``：个人视角工作台模板、第一人称代词转换、动作归属与关注度雷达图
  - ``test_supervisor_optimization.py``：短会快速放行门禁（<2000字）、事实守卫（人名/数字）与送审稿精简瘦身
  - ``test_draft_scrape.py``：草稿提炼与上下文标记提取一致性断言

- ``tests/meeting/``：会议垂直业务领域各任务线与记忆系统专项测试
  - ``test_consensus_decision.py``：共识决策模板驱动解析、门禁白名单、鲁棒小节识别与响应式 HTML 卡片
  - ``test_minutes_styles.py``：5 大黄金纪要样式规范（brief/topic/review/retro/alignment）、250-300字预算与 API 强校验
  - ``test_minutes_trace.py``：平实两级溯源结构、议题内涵加权（Jaccard）切片对齐与发言定位高亮
  - ``test_actions_risks.py``：待办与风险 Form A 现代工单/票据流卡片 Markdown 与 HTML 导出
  - ``test_agenda_minutes.py``：议程纪要 OCR 提取、时序看板对齐与 9 大会议类型推断端到端测试
  - ``test_agenda_coercion.py``：议程类型强制转换（Agenda Coercion）阈值守卫与边界行为
  - ``test_meeting_memory.py``：跨场次长期记忆状态机、事实溯源引用与向量索引回写

运行方式：
----------
    pytest tests/                              # 运行全量测试套件
    pytest tests/core/                         # 仅运行核心内核层测试
    pytest tests/meeting/                      # 仅运行会议领域业务测试
    pytest tests/meeting/test_consensus_decision.py -v  # 针对特定任务线进行单测
    python -m tests                            # 统一入口快速自测
"""
