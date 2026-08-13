# 审查结果：notes 域任务线 + 公共组件

## 0. notes_core（笔记理解）+ perspective（视角建模）+ supervisor（全局标准）

### 问题清单

- [高]（supervisor）"跨领域一致性由全局层面处理"没有任何落实者。`supervisor_prompt.py:7` 规定"跨领域一致性由全局层面处理"，但 `supervisor.py:12-24` 的 `GlobalSupervisor` 只是把同一段通用标准文本拼进各线 supervisor prompt，全系统不存在跨线交叉审核节点；points 与 knowledge_graph 两线并行生成、互不见面。→ 影响：同一概念在知识点（title 措辞）与图谱（node.name）中可能写法不一（如"偶函数"vs"偶函数的判断"），用户无法对应；`supervisor_prompt.py:3` 的"默认信任"还禁止单线 supervisor 越界评判其他线。→ 改进方向：增加跨线一致性检查节点（或由共享 notes_understanding 的 key_terms 作为两条线的唯一术语源，强制 title/node.name 从中取词）。

- [高]（perspective）视角组件对 notes 域基本空转，且空模型自带误导性置信度。`perspective/contracts.py:19-50` 的字段（inferred_role/responsibilities/goals/concerns/possible_actions/preference_signals）与 `perspective/prompts.py:13-18` 的下游表格（纪要/待办/风险/知识点/导图）全部面向会议/工作域；学生复习笔记场景下这些字段几乎全空。`perspective/models.py:61-74` 的 `EMPTY_PERSPECTIVE_MODELING` 把 `confidence` 硬编码为 `"high"`，而 `domain_engine.py:193-206` 在无画像时仍无条件调用一次 LLM。→ 影响：为每次运行多花一次调用；下游 points（`points/prompts.py:25`"可优先保留与用户兴趣/职责相关的点"）收到一个"high 置信度"的全空模型，既无信息又可能误导 LLM 以为已建模。→ 改进方向：无画像/客观模式短路不调用；notes 域改用轻量视角（relevant_topics 仅锚定 key_terms）；EMPTY 模型 confidence 改为 low 或增加"未建模"显式标记。

- [中]（notes_core）空笔记/空章节边界无确定性处理。`notes_understanding_agent.py:16-22` 直接调 LLM，`orchestrator.py:237-247` 只兜异常；契约 `note_purpose` 必填 str（`notes_core/contracts.py:13`）但 `models_generated.py:50-58` 只校验类型不校验非空。→ 影响：空 transcript 时 LLM 可能产出臆造术语或垃圾 sections；下游 points 的 importance=high 判定依赖"直接支撑 note_purpose"（`points/prompts.py:55`），空 purpose 使判定失去依据。→ 改进方向：入口对空/纯空白 transcript 短路（返回空理解+降级标记），契约层对 note_purpose 加非空校验。

- [中]（notes_core）上游"全收"与图谱下游"限量"目标冲突。`notes_core/prompts.py:86-92` 要求 key_terms"名词类知识单位全部收：公式/法则/定理/方法名/题型名/易错点…是知识图谱的节点候选"；而 `knowledge_graph/prompts.py:42-45` 规定节点"约 18–32"且"尽量 ≥20"。→ 影响：大笔记 key_terms 可达 50+，图谱被迫大量丢弃 notes_core 判定为知识单位的候选；supervisor 对照 notes_understanding 检查"关键概念遗漏"（`knowledge_graph/prompts.py:120`）时标准互相矛盾。→ 改进方向：明确 key_terms 与图谱节点的子集关系及截断优先级（候选分优先/普通两档），或给 key_terms 设上限。

- [中]（perspective）契约的 `evidence` 是扁平字符串列表，"逐条对应字段"不可执行。`perspective/contracts.py:26`（StrListField）+ `perspective/prompts.py:46`（"逐条对应字段，可定位到画像条目或原句"）→ 影响：下游无法程序化判断哪条 evidence 支撑哪个字段/attention_point，只能让 LLM 再猜；`points/contracts.py` 对 evidence 也无结构化锚。→ 改进方向：evidence 改为对象列表（{for_field, quote, basis}），或删除"逐条对应"表述。

- [中]（supervisor）"遗漏类"拦截标准不可执行且抽查模式对结构化输出不充分。`supervisor_prompt.py:3` 明确"默认信任、抽查"；`points/prompts.py:98`"遗漏明显核心知识点"、`knowledge_graph/prompts.py:120`"关键概念或明显关系遗漏"均无可操作定义。审核上下文虽含 notes理解（`orchestrator.py:204-208`），但 prompt 未要求 reviewer 逐 section 对照 sections/key_terms 核对缺失，同一遗漏在两次审核中可能 pass/fail 不同（违反 `supervisor_prompt.py:4` 一致性要求）。→ 影响：关键遗漏大概率漏网。→ 改进方向：把"对照 notes_understanding 覆盖核对"写成检查项清单；对可机械判定项（如 points.title 对 key_terms 的覆盖率、悬空边）下沉为代码校验而非 LLM 抽查。

- [低]（notes_core）`open_questions` 基本无消费者；"宁多勿漏"与"仅口头带过不收"倾向冲突。`points/prompts.py:23` 仅"一般不直接当知识点"一笔带过，`knowledge_graph/prompts.py` 完全不提 open_questions；`notes_core/prompts.py:40-41`（宁多勿漏）与 `:92`（仅口头带过→不收）给 LLM 相反倾向。→ 影响：open_questions 产出浪费；key_terms/sections 复跑抖动（违反 `notes_core/prompts.py:42` 稳定性要求）。→ 改进方向：明确 open_questions 的消费方或移除；给"收/不收"定优先级（先无据不收，再有据宁多）。

## 1. points（知识点总结）

### 问题清单

- [高] 嵌套校验完全缺失，契约枚举在代码层不生效。`models_generated.py:60-71` 的 `Points.validate` 只查 `points` 是 list，内部对象字段（title/summary/explanation/evidence/importance/review_questions）缺失、超长、`importance` 出枚举（如"重要"）全部放行；`points/contracts.py:20` 的 `EnumField` 只进 prompt 模板不参与校验。→ 影响：坏结构直达渲染与报告，仅靠 supervisor 抽查兜底。→ 改进方向：给 Points 增加嵌套校验（必填字段 + importance 枚举 + evidence 非空），与 `tools/validation.py:52-64` `_action` 的深校验先例对齐。

- [高] prompt 内部"宁缺毋滥"与"宁多勿漏"两条最高原则并存。`points/prompts.py:9-13`（"原文没有的不补充；拿不准→不提取"）vs `:67`（"复习用途下宁多勿漏（有据即可）"），且 `:21`"每个 section 至少考虑 0–N 个知识点"表述含糊。→ 影响：同一输入可能产出 3 条或 15 条，与 `:74`"同输入复跑：知识点集合与 title 措辞应稳定"自检直接冲突。→ 改进方向：把"复习用途默认宁多勿漏（有据即可）"定为唯一缺省，把"宁缺毋滥"限定为"无据不写"，删除 0–N 表述。

- [中] 三条文本字段"引用 vs 改写"标准不一，supervisor 只查一半。summary 允许"原文关键句截取拼接"（`:52`）、explanation"避免只复制原文"（`:53`）、review_questions"不整句抄原文"（`:56`），而审核只拦"explanation 引入原文外知识"（`:97`），不查 summary 是否忠实/evidence 是否可定位。→ 影响：summary 被改写走样、explanation 整段摘抄均无人把关。→ 改进方向：为三类字段明确各自允许的原文占比；拦截标准补"summary 关键数字/结论与原文不一致"。

- [中] importance 判定信号与样本笔记实际表达错位。`points/prompts.py:55` 只给"核心/重点/关键/必须掌握"作为 high 信号，而样本（`samples/notes/file/student_math_notes.txt:5,7,21,35`）实际用"考试最喜欢考""最容易丢分""必考题型""年年考""压轴"等表达；"直接支撑 note_purpose"对多主题笔记几乎恒成立。→ 影响：high/low 分布不稳定，复习优先级失真。→ 改进方向：信号词扩为覆盖"考点/易错/压轴/必考"，或把 importance 改为确定性事后规则（按信号词命中数修正）。

- [中] perspective 对 points 只有软性引导、无机制闭环。`points/prompts.py:25`"可优先保留与用户兴趣/职责相关的点"，但 Points 契约/Report（`reports.py:32-44`）无个性化标记字段（如 personal_relevance），渲染也不体现；同时共享上下文把完整用户画像 JSON 塞给生成 agent（`orchestrator.py:183`）。→ 影响：个性化对 points 实际影响≈0，还稀释上下文注意力。→ 改进方向：要么砍掉该引导，要么加"个性化标记+排序"字段形成闭环。

- [中] points 线无记忆机制，知识点无法跨次积累/去重。`tools/memory/runtime.py:24-25,84-88` 只向 meeting 与 knowledge_graph 线注入记忆；points 对同一 `--user_id + --subject` 的多次复习没有去重或合并。→ 影响：同一学科重复生成重复知识点，与图谱线的增量能力不对称。→ 改进方向：为 points 增加轻量记忆（上次 points 的 title 集合注入，提示合并/去重）。

- [低] render 无模板时 temperature=None → 走客户端默认温度（可能>0），与"内容逐字沿用草稿/同输入一致"（`points/prompts.py:121-125`）冲突；`points_render.py:28-32` 的 `except TypeError` 回退掩盖了客户端不支持 temperature 参数的兼容问题。→ 影响：渲染措辞抖动。→ 改进方向：统一 temp=0.0，显式探测客户端 API 能力而非裸捕获 TypeError。

- [低] 降级拼装缺 formatter，reject/超限路径产出自相矛盾。`points/contracts.py:40-48` 用 `Lines("points")`，但 `orchestrator.py:150-152` 的 `_LINES_FORMATTERS` 只注册了 knowledge_graph → `domain_engine_text.py:186-188` 中 points 的 Lines 段被跳过，sections 为空 → 即使草稿有内容（supervisor reject 后路由到 fallback，`domain_engine.py:331-334`），rendered 文本也是 `empty_text="暂无明确知识点"`，而 structure 仍携带 points 数据。→ 影响：被拒草稿在最终输出中显示"暂无知识点"但结构化字段有内容，文本与结构互相矛盾。→ 改进方向：为 points 注册 formatter，或 reject 路径同时清空 rendered 与 structure。

### 亮点（可选）

- evidence 必填 + "顺序=原文出现序"（`points/prompts.py:11,58`）把复习清单与原文锚定，抽查时可复核；review_questions 数量规则（默认 2、极少 1、含易错 3）具体可执行；`validate_supervisor_semantics`（`tools/validation.py:67-101`）强制 revise 必须带 feedback、approve 不得有失败项，杜绝了"revise 无意见"的空转返工。

## 2. knowledge_graph（知识图谱）

### 问题清单

- [高] 悬空边/节点一致性无确定性校验，只靠 supervisor 抽查 + 导出端静默过滤。`models_generated.py:31-39` 只查 nodes/edges 是 list；edges 的 source/target 是否存在于 nodes、relation 是否在枚举内、name 是否非空均不校验；supervisor 拦截"source/target 不在 nodes 或写法不一致"（`knowledge_graph/prompts.py:118`）但 `MAX_REVISIONS=1`（`domain_engine.py:75`）且抽查不可靠；导出端 `tools/knowledge_graph.py:264-271,412-413` 对悬空边静默 `continue`，仅打日志（`:317-321`）。→ 影响：用户看到的图缺边且无任何提示，图数据与大纲（渲染端被要求"逐字一致"，`prompts.py:142`）可能不一致。→ 改进方向：在 `KnowledgeGraph.validate` 或 agent 后处理中做确定性校验（悬空边→返工或自动剔除并计数），把剔除数量暴露到 Report/告警。

- [高] 节点 name 的唯一性规则缺失，而 name 同时充当图 id 与边引用键。导出端按 name 去重/建 id（`tools/knowledge_graph.py:203-216,386-390`），同名节点静默合并（首现者胜，后续 definition/section 丢失）；契约"name 原样引用 ≤15 字"（`knowledge_graph/contracts.py:33`）与"公式/法则/定理全收"（`prompts.py:44`）冲突——样本中的"换底公式 log_a b = log_c b / log_c a"、"f(x+a)=-f(x)" 等远超 15 字，LLM 截断或改写后，边引用（要求逐字一致，`prompts.py:66`）必然失配。→ 影响：公式类术语高概率产生悬空边/重复节点，图谱结构被静默破坏。→ 改进方向：明确"name 全图唯一 + 同名合并规则（保留 definition 更长者）"写入契约与校验；对公式术语给缩略名+definition 存全式的专门规则。

- [中] 数量控制互相矛盾且无硬上限。"约 18–32"（`prompts.py:42`）、"尽量 ≥20"（`:45`）、"扩充候选（让学生查得到的更全）"（`:44`）、"非章节节点尽量 ≥1 条边"（`:68`）、"边数建议 ≥ 节点数×60%"（`:70`）叠加，对数百行笔记可产出 100+ 节点，边数下限随节点数膨胀、为凑 60% 而造弱边；输出超长触发 structured 重试/schema_repair，graphviz fdp 布局几百节点不可读。→ 影响：图质量随输入规模劣化、成本上升。→ 改进方向：设定节点硬上限（如 60）+ 分章节截断规则；"边数≥60%"改为区间（40–80%）且"回查遗漏"限定为"存在明确关系词处"。

- [中] 记忆合并绕过 LLM 筛选，跨笔记信息无标注。`apply_graph_memory`（`tools/memory/graph.py:82-88`）在审核前把旧图全部节点/边硬合并进草稿；旧节点 section 来自旧笔记章节，导出端章节着色/图例混入旧章节名（`tools/knowledge_graph.py:213-216,449-456`）；旧边 evidence 指向旧笔记原文，HTML 点击边直接显示旧 evidence（`:659`），与"新边 evidence 必须能在本篇定位"（`prompts.py:25`）冲突，而 supervisor 被告知"旧边保留不算编造"（`:117,122`）无法识别跨笔记污染。→ 影响：用户看到跨笔记混合图，旧证据无法在本篇核对。→ 改进方向：合并时给旧节点/边打"来源笔记"标记并在导出端分组/标注，或合并前丢弃旧 section 字段。

- [中] 不传模板时树形大纲退化为仅一行标题，且图类产物无文本出口。`orchestrator.py:225-233` 的 `_pre_render_hook` 把 rendered 直接写成 `# {draft.title}`；`save_all_reports` 又跳过 knowledge_graph 线（`tools/outputs.py:173-174`）。→ 影响：不传模板的用户拿不到任何树形/文本大纲（markmap 视图为空），唯一产物是图。→ 改进方向：无模板时用确定性算法（按 section/relation 生成 markdown 大纲）替代单行标题，或至少列出节点清单。

- [中] reject/降级不阻止图谱导出，门禁对图类产物失效。reject 路由到 fallback 节点（`domain_engine.py:331-334`），但 `orchestrator.py:291-297` 的 fallback 只改 rendered/structure、不清空 draft → `_final_reports` 仍从 draft.nodes/edges 组装 Report（`reports.py:59-66`），`export_knowledge_graph`（`tools/outputs.py:221-237`）照常导出被拒图的 PNG/SVG/HTML，且不检查 quality_warning。→ 影响：被审拒的图仍成为正式产物。→ 改进方向：reject 路径清空 draft，或导出加 degraded 门控。

- [中] relation 契约枚举与导出端样式表不一致。契约允许 13 种关系（`knowledge_graph/contracts.py:49-53`），`tools/knowledge_graph.py:41-50` 的 `_RELATION_COLORS` 只含 8 种，"区别于/取决于/导致/缓解/示例"在 PNG/SVG 全部落默认灰，虚线样式只对"相关/示例"生效（`:281-284`）。→ 影响：图例无法区分契约允许的关系类型。→ 改进方向：同步枚举与样式表，或导出端对未知关系给默认样式并告警。

- [中] 章节锚点判定脆弱，无章节笔记退化。`_is_section_anchor` 要求 `name==section` 且非空（`tools/knowledge_graph.py:136-139`）；无显式章节时 notes_core 在概念切换处划分、title 用核心短语（`notes_core/prompts.py:50-54`），图谱线（`prompts.py:21,38`）没有无章节时的兜底层级策略 → 无锚点节点，`属于/包含` 层级缺失，图退化为扁平词表，与"成图优先"（`:9`）矛盾。→ 改进方向：无章节时以 note_purpose 建根节点 + 概念簇自组织，写入 prompt。

- [低] 记忆注入携带全量图 JSON，随积累膨胀。`inject_graph`（`tools/memory/graph.py:43-54`）把全部 nodes/edges 的 JSON payload 注入共享上下文，且输出需保留全部旧节点。→ 影响：积累几百节点后每次运行上下文与输出持续膨胀，成本与延迟上升。→ 改进方向：注入时按本次 sections/key_terms 相关子图裁剪，或只注入前 N 节点摘要。

---

**总结**：notes 域两条线的共性薄弱环节有三——(1) 结构校验普遍停留在第一层（Points/KnowledgeGraph 嵌套对象、枚举、悬空边全不校验），大量"契约里写了、prompt 里要求了、代码不检查"的软约束被甩给抽查式 supervisor 兜底；(2) 上游（notes_core 术语全收、记忆全量合并）与下游（图谱限量、本篇锚定）的目标冲突没有对齐，且 points 与 knowledge_graph 两条并行线之间没有任何一致性机制，"跨领域一致性"只是 supervisor_prompt 里的一句空话；(3) 降级/门禁路径对两类产物不完整——points 降级缺 formatter 导致文本与结构矛盾、rejected 图谱仍照常导出 PNG/SVG/HTML、无模板时树形大纲退化为单行标题，图类产物的"门禁"语义实际不存在。
