# 审查结果：meeting 域任务线

## 1. minutes_generation（纪要）

### 问题清单
- [高] 个人视角的裁剪指令被硬执行静默撤销：`prompts.py` L95 要求 risks_and_blockers/unresolved_questions「个人视角只保留直接影响用户的条目」，但 `minutes_generation_agent.py` L34 `enforce_minutes_draft`（`hard_execution.py` L96-102 无条件 `out[dst]=_as_str_list(upstream.get(src))`）在返回前把三项硬拷贝为理解的全量列表 → 个人模式下纪要仍输出全量风险/未决，裁剪功能实际失效，且 supervisor 看到的草稿与「与上游一致」恒成立 → 改进方向：把个人裁剪也程序化（硬拷贝后按视角过滤），或从 prompt 删除该指令。
- [中] 搬运字段的措辞修正指令是无效功且误导：`prompts.py` L88「允许补主语/连接词成句、按原文修正错字漏字」、L39「你仍应保持理解一致以便审核对照」——但输出会被程序覆盖，模型对搬运字段做的任何修改都被丢弃 → 模型做了无用功，且以为自己的修正会保留 → 改进方向：prompt 明确「搬运字段由程序写入，你无需输出（可只留空占位）」。
- [中] supervisor 上下文缺少记忆摘录原文，记忆相关检查无法核验：领域 prompt `prompts.py` L140/L154/L158 要求核对「记忆摘录都没有的事实」「历史误用」「不拦截程序写入的记忆行」，但 `orchestrator.py` `_supervisor_context`（L339-359）只注入 原文/画像/理解/视角模型/草稿，不含 `line_extra` 记忆块（`tools/memory/runtime.py` L24-88 记忆只注入 agent 上下文）→ 审核者无法区分草稿摘要中的记忆行是真是假、是否被改写为新决策 → 改进方向：supervisor 上下文补注入记忆摘录原文，或移除无法核验的记忆检查。
- [中] 审核契约模板把说明文字渲染成示例值，LLM 可能照抄：`contracts.py` L33-37 的 Feedback/Check desc 经 `tools/contracts.py` L78-84 生成 `"findings": ["仅记录严重问题"]`、`"feedback": ["仅当 decision=revise 时填写…"]`，而 `llm_client/client.py` L467-471 强制「字段与模板完全一致」；`tools/validation.py` L96-99 只校验 feedback 非空 → 照抄模板文字可通过校验，返工反馈变空泛 → 改进方向：模板中 findings/feedback 用空数组 `[]` 占位，说明文字移到注释区。
- [中] 「一次调用双重评判」叠加全局放行偏向，关键遗漏拦截弱：`supervisor/supervisor.py` L27-36 把 `GLOBAL_SUPERVISOR_PROMPT`（L11「默认信任/只拦实质误解」）拼在领域规则前，纪要领域 prompt L168 又写「写不出具体返工意见 → approve。犹豫 → approve」，且 `domain_engine.py` L75 `MAX_REVISIONS=1` → 全局「默认信任」稀释领域「遗漏关键即 revise」（L144），关键决策/时限遗漏大概率放行 → 改进方向：明确领域拦截标准优先于全局默认信任，或去掉「犹豫即 approve」。
- [中] 「主语补全」与「有据才写」自相矛盾：`prompts.py` L115 要求按上下文「补全最可能的主语（王总/合作局…）」，与 L108「本场未出现的人名不要补」、L126「有据才写」直接冲突 → 摘要/执行要点可能补出原文没有的归属人名（幻觉高发点）→ 改进方向：限定补全仅当主语在本场别处出现过，否则省略主语。
- [中] 摘要条数口径在契约与 prompt 间冲突：`contracts.py` L21 desc「通常2-3条」vs `prompts.py` L61「固定 3 槽位、每槽 1-3 条」（最多 9 条），两者同时拼进 system prompt → 模型对条数目标摇摆、复跑不稳定 → 改进方向：统一为同一口径（如「≤9 条，槽位有内容才写」）。
- [中] 搬运字段的「与上游不一致」检查是恒真检查：`prompts.py` L145 拦截「搬运字段与理解条数/顺序/措辞偏离」，但草稿三项已被 `hard_execution.py` L106-110 硬拷贝，supervisor 永远看不到偏离 → 该检查占审核预算零产出 → 改进方向：删除该项，把预算转给「提炼字段是否丢掉理解中的关键决策/数字」。
- [低] `extract_labeled_json` 失败时静默清空三项：`minutes_generation_agent.py` L33-35——若共享上下文「会议理解」块格式漂移（label/缩进变化），`extract_labeled_json` 返回 None，`enforce_minutes_draft` 把决策/风险/未决置 `[]`，无日志、无 degraded 标记 → 纪要关键内容静默丢失 → 改进方向：解析失败时打 warning 并置 quality_degraded，或直接从 state 取 meeting_understanding 而非二次解析文本。

### 亮点
- 搬运字段程序硬拷贝（agent L34 + `MINUTES_CARRY_MAP` 配置化）是防漂移的好设计，把「稳定性根基」从模型自觉变成了程序保证。
- 记忆摘录由程序前置到摘要（`apply_memory_display`），职责边界清晰，避免了模型把历史写成本场事实。
- 降级拼装声明式（`MinutesFallbackRules`）与渲染 prompt 分离，空态/免责文案完整。

## 2. action_items（待办）

### 问题清单
- [高] 个人模式的 `delegated_actions` 被提取却永不输出：`prompts.py` L66 收集「他人明确负责」到 delegated_actions，但渲染 prompt L148 顺序只含 my_actions→unassigned_actions、`action_items_render.py` L52-70 `extract_actions` 个人模式只取 my_actions、`contracts.py` L52-58 fallback 的 structured merge 也只并 my+unassigned → 他人承诺在个人视角输出中静默消失；且渲染 prompt 无模式分支（LLM 可能把 unassigned 也写进文本），与结构输出（个人模式不含 unassigned）不一致 → 改进方向：三处（渲染 prompt / extract_actions / fallback）统一个人模式口径，不输出就从提取阶段去掉。
- [高] 嵌套项生成期零校验 + 终局校验失败全量级联：`models_generated.py` L22-39 `ActionItems.validate` 只查顶层三个 list 类型（浅校验），嵌套 item 的 7 字段只在 Report 终验被 `tools/validation.py` L52-64 `_action` 严格检查（字段完全一致、task/evidence 非空）；任一 item 缺字段 → `domain_engine.py` L913-920 `_final_reports` 抛异常 → **全部任务线一起**退回确定性 fallback，连好的纪要/风险输出也被替换；schema_repair 因生成期浅校验通过而永远不触发 → 改进方向：生成契约加嵌套 item 结构校验（生成期拦截并 repair），或终验失败只降级该线。
- [中] 契约模板 desc 双用污染：`contracts.py` L22-27 的说明文字（如「无明确负责人时为null」）被渲染成 `"owner": "原文明示的负责人姓名，无明确负责人时为null"` 示例值，叠加 `client.py` L467-471「与模板完全一致」 → LLM 可能把整句说明当值输出，owner 变成说明文字而非 null → 改进方向：模板值用 `""`/`null`/`[]` 占位，说明移出模板。
- [中] 个人模式 unassigned 的 evidence 语义与契约/审核规则冲突：`prompts.py` L67 要求 evidence 写「职责匹配，非直接分配」说明，而 `contracts.py` L26 定义 evidence 为「原文支撑语句」、supervisor 拦截标准 L129「evidence 无具体原句→revise」 → 这些 item 必然带非原句 evidence，可能被误判 revise → 改进方向：明确 evidence 允许「匹配说明」例外，或单设字段。
- [中] `status` 字段规则自相矛盾且是死字段：`prompts.py` L85「explicit=任务+负责人均明示；负责人不可 inferred」——unassigned 项 owner 恒为 null，既非 explicit 又禁止 inferred，无合法取值；且 status 在渲染（`action_items_render.py` L79-88）与结构输出中从未被消费 → 语义含混且浪费输出/审核预算 → 改进方向：删除 status，或定义与负责人无关的取值规则。
- [中] 审核维度最薄：`contracts.py` L39-41 只有 1 个检查项且领域 prompt L135 明示「抽查」；`MAX_REVISIONS=1`（`domain_engine.py` L75） → 抽查 + 一次返工对「归属错误/编造/关键遗漏」这类高代价错误覆盖不足 → 改进方向：拆成 归属/字段依据/遗漏 三维检查，至少对 high/显式项全量核验。
- [低] 降级格式化 KeyError 可致整次运行崩溃：`action_items_render.py` L89 `item['task']` 直接索引（对比 `domain_engine_text.py` L134-151 `format_risk_item` 全部 `.get` 安全）——嵌套零校验放行的缺 task 项，会让 fallback 节点（`orchestrator.py` L505-511）和 `_fallback_reports`（`domain_engine.py` L677-698）抛 KeyError，且后者在 `run_streaming` 的 except 内调用（L829-848），二次异常直接冒泡 → 单条畸形待办可拖垮整次运行 → 改进方向：改 `item.get("task") or ""`，fallback 前过滤缺 task 项。
- [低] 降级格式化与渲染 prompt 的元信息顺序不一致：`prompts.py` L147 顺序「负责人、截止、高/低优先」，`format_action`（`action_items_render.py` L79-88）顺序「优先、负责人、截止」，docstring 却声称「与 LLM 渲染 prompt 的格式约定一致」 → 正常渲染与降级文本的行格式漂移 → 改进方向：统一顺序或删去一致性声明。

### 亮点
- 两阶段流程（全量罗列→五关精筛）+「拿不准→不提取/unassigned」的兜底边界清晰，是最能抑制幻觉的一条线。
- priority 默认 medium、high 须 evidence 信号词的确定性规则落地明确。
- 结构化 Report（structure 字段）与渲染文本双轨输出，机器可消费。

## 3. risk（风险分析）

### 问题清单
- [中] source 规则与默认 severity 自相矛盾：`prompts.py` L49「source 须含支撑 severity 的原文措辞」+ L50「否则一律 medium」——medium 本就是「无信号」默认值，无支撑措辞可言 → LLM 要么为 medium 硬凑 source 措辞（失真），要么违反规则 → 改进方向：区分「high/low 须 source 含信号措辞；medium 无此要求」。
- [中] 契约模板 desc 污染（同前两条线）：`contracts.py` L16-21 desc 渲染成示例值 `"impact": "如果风险发生，可能造成的影响"`、`"mitigation": "原文中已有的应对措施；没有则为null"`，`client.py` L467-471 强制模板一致 → LLM 可能把说明文字当值输出，或把「没有则为null」当字面值 → 改进方向：模板值用 `null` 占位，说明移出模板。
- [中] risk 嵌套项零校验，畸形项直达输出：`models_generated.py` L140-145 与 L461-488 均只查 `risks` 是 list，不校验 item 字段——缺 risk/severity 等字段的项不会触发任何结构校验/repair → 渲染端面对缺字段项（如 `format_risk_item` L149 兜底成 `"1. （来源：…）"` 空行错位）→ 改进方向：为 risk 项加与 `_action` 等价的嵌套校验，缺字段触发 schema repair。
- [中] supervisor 领域规则缺少视角模式维度：`prompts.py` L77-96 无「模式选择」段落（对比纪要 L132-136、待办 L119-121 都有），`contracts.py` L31-33 也只有一个 risk_check → 个人模式下风险输出无「是否遗漏用户相关风险/是否偏向」的把关 → 改进方向：补个人/客观模式审核维度。
- [中] 跨线风险集合不一致且无人协调：风险线允许「补充上游漏掉但原文有信号的风险」（`prompts.py` L19），而纪要线 risks_and_blockers 硬拷贝 `understanding.risks`（`hard_execution.py` L106-110）→ 风险线多发现的风险不会进纪要，同一风险两线措辞/严重度也可能不同；`supervisor_prompt.py` L17 声称「跨领域一致性由全局层面处理」，但 `supervisor.py` L27-36 显示全局监督器从不单独发起调用 → 跨线一致性实际无人把关 → 改进方向：纪要线搬运源改为「理解 + 风险线输出」并集（或明确纪要只反映理解层风险并加注）。
- [低] severity 在理解层缺失，两线无法对照：理解模型（`meeting_core/contracts.py` L27）risks 只有字符串列表，无严重度；风险线的 severity 是独立再判定的，与纪要风险无对应关系 → 用户对照两线输出时无法判断优先级是否一致 → 改进方向：允许风险线 severity 回写/对齐纪要（或加来源标注）。

### 亮点
- severity 默认 medium + high 需强信号的确定性规则，抑制夸大。
- 「顺序=原文出现序、勿按严重程度重排」的稳定性设计明确。
- impact/mitigation/owner 的「无→null」边界清晰，且 `format_risk_item` 全程 `.get` 安全。

## 共性薄弱环节总结
三条线的共同短板是：① 契约 DSL 把字段/检查项说明当作示例值渲染进「唯一合法输出模板」，叠加 structured() 的模板一致性强约束，LLM 有照抄说明文字当真实值的系统性风险（supervisor 的 findings/feedback 尤甚，且只查非空校验放行）；② 生成模型与 Report 对嵌套对象全部浅校验或零校验，畸形项要么拖到终局才被发现并级联拖垮全部任务线（action_items），要么永远不被发现（risk），schema_repair 实际覆盖不到嵌套层；③ supervisor 是「一次调用 + 全局默认信任/犹豫即 approve + 最多 1 次返工」的强放行结构，且关键事实源（记忆摘录）未注入审核上下文、跨线一致性无人实现，导致审核环节的纠错能力被系统性稀释。
