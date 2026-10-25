# 工业级标准化日志系统重构计划 (ACTION_PLAN_LOGGING_REFACTOR.md)

## 一、 重构背景与核心目标

当前系统的日志输出存在三个核心问题：
1. **关键业务上下文缺位**：任务启动日志中缺乏当前执行语种（`lang=zh/en`），以及 `texts` 四字段载荷（`transcript`, `keypoints`, `notes`, `vision_info`）的有效性、数量与字符规模统计，排查时无法获知多源数据是否成功注入；
2. **格式松散且不统一**：既有日志混杂了 `[task:start]` 括号前缀、`agent start gen line=minutes` 纯英文口语句、`saved html ...` 无前缀短语等多种风格，不利于工业级日志收集器（ELK / Loki / CloudWatch / Datadog）结构化抽取与监控告警；
3. **Agent 节点跳过（Skip）与决策缺乏规范表达**：会议理解、视角建模、Supervisor 快速短路（fast-path）等跳过逻辑输出格式不规整，无法一目了然区分哪些节点正常执行、哪些因何种业务规则被豁免。

### 重构准则
- **工业级标准**：全链路统一采用 `[module:action] key1=val1 key2=val2 ...` 标准键值对（Structured Key-Value Logging）；
- **零 Emoji、零废话**：全面移除所有表情符号与 ASCII 树状图，语言严谨平实、高度紧凑；
- **全链路保真**：完整保留任务接入、载荷分析、Agent 启停、跳过豁免、模型调用消耗（Token/耗时）、审核复核、返工与产物落盘的全生命周期事件；
- **路径规范化**：落盘文件统一输出规范相对路径，消除长绝对路径刷屏。

---

## 二、 统一事件标签与字段字典规范

| 标准标签 | 触发阶段 | 标准输出字段字典 | 释义与业务价值 |
|---|---|---|---|
| `[task:start]` | 任务接入启动 | `domain`, `task`, `req_id`, `user_id`, `lang`, `memory` | 记录任务基本元数据，显式透传语种 |
| `[task:payload]` | 输入载荷解析 | `lang`, `transcript`, `keypoints`, `notes`, `vision`, `aux` | **核心亮点**：直观展示 4 字段规模、引语/批注过滤统计、OCR 字符及辅助包注入规模 |
| `[agent:start]` | Agent 启动执行 | `name`, `line`, `mode`, `lang`, `aux` | 记录 Agent 启动时的运行模式、语种微调及挂载的多源指令块 |
| `[agent:skip]` | Agent 豁免跳过 | `name`, `line`, `reason` | **关键补齐**：显式说明跳过原因（如自包含议程单、客观视角、字符门禁等） |
| `[agent:done]` | Agent 执行产出 | `name`, `line`, `dur`, `chars`/`words`/`segments`, `status` | 记录 Agent 耗时与产出成果规模 |
| `[agent:review]` | 审核复核裁决 | `line`, `decision`, `score`, `aux_safe`, `reason`, `dur` | 记录 Supervisor 裁决（approve/reject）、打分及多源吐槽词/数据一致性审查结果 |
| `[llm:done]` | 模型调用完成 | `label`, `dur`, `prompt_tokens`, `completion_tokens` | 记录每次结构化/自由文本大模型交互的耗时与 Token 消耗 |
| `[render:start/done]` | 产物渲染流 | `line`, `dur` | 记录 HTML/卡片渲染流水线启停与耗时 |
| `[export:done]` | 文件产物落盘 | `line`, `format`, `path`, `chars` | 记录生成的 HTML / Markdown 相对路径与文件字符数 |
| `[task:finish]` | 任务最终归档 | `req_id`, `dur`, `total_tokens`, `status` | 记录整条任务流水线的端到端总耗时、总消耗 Token 与最终状态 |
| `[task:failed]` | 任务异常终止 | `req_id`, `dur`, `error`, `status` | 记录任务失败原因与定位信息 |

---

## 三、 标准输出示例（场景覆盖）

### 场景 1：普通纪要（中文 + 4 字段全量多源输入 + 客观全员模式）
```log
2026-10-25 14:00:01 [INFO] [app.tasks] [task:start] domain=meeting task=minutes req_id=req_8f92a user_id=u_001 lang=zh memory=false
2026-10-25 14:00:01 [INFO] [app.tasks] [task:payload] lang=zh transcript=14.2k_chars keypoints=3_items(180_chars) notes=4_quotes/2_comments vision=520_chars aux=injected(820_chars)
2026-10-25 14:00:01 [INFO] [agentflow] [agent:start] name=meeting_understanding lang=zh
2026-10-25 14:00:04 [INFO] [infra.llm] [llm:done] label=meeting_understanding dur=2.85s prompt_tokens=4210 completion_tokens=650
2026-10-25 14:00:04 [INFO] [agentflow] [agent:done] name=meeting_understanding dur=2.86s segments=4 decisions=3 open_questions=2
2026-10-25 14:00:04 [INFO] [agentflow] [agent:skip] name=perspective reason=objective_mode
2026-10-25 14:00:04 [INFO] [agentflow] [agent:start] name=minutes_draft line=minutes mode=objective lang=zh aux=keypoints,notes,vision
2026-10-25 14:00:07 [INFO] [infra.llm] [llm:done] label=minutes/agent/objective dur=3.42s prompt_tokens=5120 completion_tokens=1850
2026-10-25 14:00:07 [INFO] [agentflow] [agent:done] name=minutes_draft line=minutes dur=3.44s chars=2340 sections=3
2026-10-25 14:00:07 [INFO] [agentflow] [agent:start] name=minutes_review line=minutes
2026-10-25 14:00:08 [INFO] [infra.llm] [llm:done] label=minutes/supervisor/objective dur=0.91s prompt_tokens=3250 completion_tokens=120
2026-10-25 14:00:08 [INFO] [agentflow] [agent:review] line=minutes decision=approve score=96 aux_safe=true dur=0.92s
2026-10-25 14:00:08 [INFO] [agentflow] [render:start] line=minutes
2026-10-25 14:00:09 [INFO] [agentflow] [render:done] line=minutes dur=0.31s
2026-10-25 14:00:09 [INFO] [core.runner] [export:done] line=minutes format=html path=data/u_001/output/req_8f92a/minutes/minutes.html chars=2340
2026-10-25 14:00:09 [INFO] [app.tasks] [task:finish] req_id=req_8f92a dur=8.53s total_tokens=15200 status=success
```

### 场景 2：普通纪要（英文 + 纯语音转写，无额外辅助字段）
```log
2026-10-25 14:05:01 [INFO] [app.tasks] [task:start] domain=meeting task=minutes req_id=req_3b11c user_id=u_002 lang=en memory=false
2026-10-25 14:05:01 [INFO] [app.tasks] [task:payload] lang=en transcript=8.5k_chars keypoints=none notes=none vision=none aux=none
2026-10-25 14:05:01 [INFO] [agentflow] [agent:start] name=meeting_understanding lang=en
2026-10-25 14:05:03 [INFO] [infra.llm] [llm:done] label=meeting_understanding dur=2.10s prompt_tokens=2800 completion_tokens=420
2026-10-25 14:05:03 [INFO] [agentflow] [agent:done] name=meeting_understanding dur=2.11s segments=3 decisions=2 open_questions=0
2026-10-25 14:05:03 [INFO] [agentflow] [agent:skip] name=perspective reason=objective_mode
2026-10-25 14:05:03 [INFO] [agentflow] [agent:start] name=minutes_draft line=minutes mode=objective lang=en aux=none
2026-10-25 14:05:06 [INFO] [infra.llm] [llm:done] label=minutes/agent/objective dur=2.75s prompt_tokens=3950 completion_tokens=1280
2026-10-25 14:05:06 [INFO] [agentflow] [agent:done] name=minutes_draft line=minutes dur=2.76s words=1820 sections=3
2026-10-25 14:05:06 [INFO] [agentflow] [agent:start] name=minutes_review line=minutes
2026-10-25 14:05:07 [INFO] [infra.llm] [llm:done] label=minutes/supervisor/objective dur=0.82s prompt_tokens=2400 completion_tokens=90
2026-10-25 14:05:07 [INFO] [agentflow] [agent:review] line=minutes decision=approve score=92 aux_safe=none dur=0.83s
2026-10-25 14:05:07 [INFO] [agentflow] [render:start] line=minutes
2026-10-25 14:05:08 [INFO] [agentflow] [render:done] line=minutes dur=0.25s
2026-10-25 14:05:08 [INFO] [core.runner] [export:done] line=minutes format=html path=data/u_002/output/req_3b11c/minutes/minutes.html words=1820
2026-10-25 14:05:08 [INFO] [app.tasks] [task:finish] req_id=req_3b11c dur=6.75s total_tokens=10940 status=success
```

### 场景 3：议程纪要 / 议程增强（跳过会议理解 Skip 典型场景）
```log
2026-10-25 14:08:01 [INFO] [app.tasks] [task:start] domain=meeting task=agenda_minutes req_id=req_5a22d user_id=u_001 lang=zh memory=false
2026-10-25 14:08:01 [INFO] [app.tasks] [task:payload] lang=zh transcript=18.0k_chars keypoints=none notes=none vision=none aux=none docs=agenda.png
2026-10-25 14:08:01 [INFO] [agentflow] [agent:skip] name=meeting_understanding reason=agenda_minutes_self_contained
2026-10-25 14:08:01 [INFO] [agentflow] [agent:skip] name=perspective reason=agenda_minutes_self_contained
2026-10-25 14:08:01 [INFO] [agentflow] [agent:start] name=agenda_minutes_agent line=agenda_minutes mode=agenda lang=zh
2026-10-25 14:08:05 [INFO] [infra.llm] [llm:done] label=agenda_minutes/agent dur=4.12s prompt_tokens=6200 completion_tokens=2100
2026-10-25 14:08:05 [INFO] [agentflow] [agent:done] name=agenda_minutes_agent line=agenda_minutes dur=4.14s agendas=5
...
```

### 场景 4：异常拦截与返工（笔记主观吐槽词被拦截 -> Rework -> 最终 Approve）
```log
2026-10-25 14:10:01 [INFO] [app.tasks] [task:start] domain=meeting task=minutes req_id=req_7e44a user_id=u_001 lang=zh memory=false
2026-10-25 14:10:01 [INFO] [app.tasks] [task:payload] lang=zh transcript=10.1k_chars keypoints=none notes=2_quotes/1_comments vision=none aux=injected(310_chars)
2026-10-25 14:10:01 [INFO] [agentflow] [agent:start] name=meeting_understanding lang=zh
2026-10-25 14:10:03 [INFO] [infra.llm] [llm:done] label=meeting_understanding dur=2.30s prompt_tokens=3100 completion_tokens=520
2026-10-25 14:10:03 [INFO] [agentflow] [agent:done] name=meeting_understanding dur=2.31s segments=3 decisions=1 open_questions=1
2026-10-25 14:10:03 [INFO] [agentflow] [agent:skip] name=perspective reason=objective_mode
2026-10-25 14:10:03 [INFO] [agentflow] [agent:start] name=minutes_draft line=minutes mode=objective lang=zh aux=notes
2026-10-25 14:10:06 [INFO] [infra.llm] [llm:done] label=minutes/agent/objective dur=3.05s prompt_tokens=4120 completion_tokens=1450
2026-10-25 14:10:06 [INFO] [agentflow] [agent:done] name=minutes_draft line=minutes dur=3.06s chars=1950 sections=3
2026-10-25 14:10:06 [INFO] [agentflow] [agent:start] name=minutes_review line=minutes
2026-10-25 14:10:07 [INFO] [infra.llm] [llm:done] label=minutes/supervisor/objective dur=0.92s prompt_tokens=2850 completion_tokens=180
2026-10-25 14:10:07 [WARN] [agentflow] [agent:review] line=minutes decision=reject score=45 aux_safe=false reason="leaked_subjective_comment:扯淡" dur=0.93s
2026-10-25 14:10:07 [INFO] [agentflow] [agent:start] name=minutes_rework line=minutes attempt=1/1
2026-10-25 14:10:10 [INFO] [infra.llm] [llm:done] label=minutes/agent/rework dur=2.78s prompt_tokens=4300 completion_tokens=1420
2026-10-25 14:10:10 [INFO] [agentflow] [agent:done] name=minutes_rework line=minutes dur=2.80s chars=1920 sections=3
2026-10-25 14:10:10 [INFO] [agentflow] [agent:start] name=minutes_review line=minutes
2026-10-25 14:10:11 [INFO] [infra.llm] [llm:done] label=minutes/supervisor/objective dur=0.85s prompt_tokens=2800 completion_tokens=90
2026-10-25 14:10:11 [INFO] [agentflow] [agent:review] line=minutes decision=approve score=95 aux_safe=true dur=0.86s
2026-10-25 14:10:11 [INFO] [agentflow] [render:start] line=minutes
2026-10-25 14:10:12 [INFO] [agentflow] [render:done] line=minutes dur=0.28s
2026-10-25 14:10:12 [INFO] [core.runner] [export:done] line=minutes format=html path=data/u_001/output/req_7e44a/minutes/minutes.html chars=1920
2026-10-25 14:10:12 [INFO] [app.tasks] [task:finish] req_id=req_7e44a dur=11.35s total_tokens=22110 status=success
```

---

## 四、 实施路径与执行清单

### 阶段一：入口层与载荷提取日志升级 (app/tasks.py)
- [x] 1.1 在 `app/tasks.py` 的 `_run_task_impl` 中，升级 `[task:start]` 格式，加入 `lang=%s`；
- [x] 1.2 在 `_prepare` 阶段提取 `_collect_texts` 后，新增 `[task:payload]` 日志函数，按规格计算并打印 `transcript`, `keypoints`, `notes`, `vision`, `aux` 统计；
- [x] 1.3 升级 `[task:finish]` 与 `[task:failed]`，统一字段标签为标准 KV。

### 阶段二：编排内核与 Agent 生命周期标准化 (core/graph/nodes.py)
- [x] 2.1 视角建模节点：将 `progress("skip perspective (objective)")` 替换为 `progress("[agent:skip] name=perspective reason=objective_mode")`，统一 `[agent:start]` 与 `[agent:done]`；
- [x] 2.2 草稿生成节点：`_make_agent_node` 输出 `[agent:start] name={line}_draft line={line} mode={mode} lang={lang} aux={aux}`，完成后输出 `[agent:done] ...`；
- [x] 2.3 审核监督节点：`_make_supervisor_node` 快速放行时输出 `[agent:skip] name={line}_review line={line} reason={fast_path_chars/guardrail_pass}`，完成时输出 `[agent:review] line={line} decision={d} score={s} aux_safe={a} dur={dur}`；
- [x] 2.4 返工重做节点：`_make_rework_node` 规范输出 `[agent:start] name={line}_rework attempt={attempt}`；
- [x] 2.5 渲染流节点：`[render:start] line={line}` 与 `[render:done] line={line} dur={dur}`。

### 阶段三：会议领域特定跳过与底座日志标准化 (domains/meeting/orchestrator.py)
- [x] 3.1 会议理解跳过（议程自包含）：将 `progress("skip meeting_understanding (agenda_minutes self-contained)")` 标准化为 `[agent:skip] name=meeting_understanding reason=agenda_minutes_self_contained`；
- [x] 3.2 议题纪要增强跳过：`progress("skip meeting_understanding (minutes agenda enhanced self-contained)")` 标准化为 `[agent:skip] name=meeting_understanding reason=minutes_agenda_enhanced_self_contained`；
- [x] 3.3 会议理解正常执行：规范输出 `[agent:start] name=meeting_understanding lang={lang}` 及完成时的指标摘要统计。

### 阶段四：基础设施模型调用与产物导出标准化 (infra/llm/llmclient.py, core/runner/runner.py)
- [x] 4.1 在 `infra/llm/llmclient.py` 中，保持 INFO 级别只输出单行紧凑 `[llm:done] label={label} dur={dur}s prompt_tokens={p} completion_tokens={c}`，移除啰嗦的调试配置日志或降级为 DEBUG；
- [x] 4.2 在 `core/runner/runner.py` 中，落盘日志由 `saved html line=...` 规范化为 `[export:done] line={line} format=html path={rel_path} chars={chars}`。

### 阶段五：测试覆盖与回归验证
- [x] 5.1 编写专用单元测试 `tests/unit/core/test_structured_logging.py` 验证各标签格式合法性；
- [x] 5.2 全量运行 `pytest tests/core/test_core.py tests/unit/meeting/ tests/meeting/` 确保零破坏、零回归。
