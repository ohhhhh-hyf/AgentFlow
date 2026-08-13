# 审查结果：meeting 域任务线（后三条 + 会议理解）

## 0. meeting_core（会议理解，公共底座）

### 问题清单

- **[中] 场景判定是"内部认知"，没有输出通道，下游用更弱的启发式重造**：`prompts.py` L25 明确要求理解 agent"scene 只需在内部判明，不必单独输出"，但 `minutes_trace/scene.py` L211-243 又用关键词启发式在 `meeting_purpose + 整篇原文` 上重新判场景，两处判定互不知情且必然可能冲突（理解认为脑暴会，启发式因原文含"风险"二字判成"项目决策与评审"）。→ 影响：溯源纪要的场景骨架（侧重与结论小节）可能选错，且核心层承诺的"场景判定"形同虚设。→ 改进方向：把 scene 加入 `MeetingUnderstandingGenerationContract` 作为枚举输出字段，让下游直接消费理解结果，启发式只作兜底。

- **[中] decisions 判定面过宽、软硬边界模糊，且无任何机制校验**：`prompts.py` L62 把"要求/必须/务必/请…做好/希望…落实/需…完成"全部计入 decisions，与 L66 的"建议/我觉得/我认为/暂定"仅靠措辞区分；同一句"希望各部门尽快落实"既可判决策也可判讨论。同时 decisions/risks/open_questions"按原文出现序"（L118/L128）与 topics"按首次提及序"（L103）多套排序并存，`models_generated.py` L51-60 只做顶层类型浅校验，条数与顺序全无门禁。→ 影响：常见会议 decisions 膨胀，直接传导给纪要/思维导图/待办三条以 decisions 为骨架的下游。→ 改进方向：给 decisions 配"信号词+拍板意图"的 few-shot 对并设条数软上限；排序约束收敛为单一规则并在自检里只保留一条主排序。

- **[低] 契约模板把 desc 当示例值，null 表达有歧义**：`contracts.py` L22 的 `conclusion` desc 是"该议题的结论，无结论时为null"，经 `to_json_template()` 变成 `"conclusion": "该议题的结论，无结论时为null"`，LLM 可能输出字符串 `"null"` 而非 JSON null（依赖 structured() 的"未知文本使用 null"规则与 schema repair 兜底）；且 topics 元素无嵌套校验，缺 conclusion/participants 键也放行。→ 影响：下游 `topic.get("conclusion")` 拿到 `"null"` 字符串时语义失真。→ 改进方向：契约模板直接给 `null` 字面示例；对 topics 元素做键存在性浅校验。

- **[中] 转写占位符清洗只有 prompt 承诺，无一层程序兜底**：`prompts.py` L46-52 强制"发言者 N 不进 participants、不得保留在字段里"，但全链路（orchestrator 落库、shared_context 注入、各线 agent）没有任何后置清洗；`structure.py` L15 的 `_SPEAKER` 正则只用于检测不用于清洗。→ 影响：理解一旦漏改，"发言者1"会随 decisions/discussion 污染思维导图/纪要/待办全部产物。→ 改进方向：理解结果落库后做一次确定性占位符清洗（删或替换）。

## 1. mindmap（思维导图）

### 问题清单

- **[中] supervisor 领域 prompt 的三检查清单与契约字段对不上**：`prompts.py` L149 写"### 检查：facts_check / structure_check / consistency_check"，但契约只有单一 `mindmap_check`（`contracts.py` L37-41，生成模型 `models_generated.py` L229-251 也只有一个字段），且这三类问题被塞进一个桶，反馈无法按维度给出。→ 影响：审核维度名存实亡，模型按提示填了不存在的字段名。→ 改进方向：契约扩为三个 check，或删掉领域 prompt 里的三检查清单、合并进 mindmap_check 的 desc。

- **[中] title 是"死字段"，与大纲根标题的一致性无任何强制**：生成 prompt 要求"outline 根 `# title` 与 title 字段一致"（`prompts.py` L26、L132），渲染 prompt 只要求"根必须 `# `"（L161），但 `MindmapReport` 只收 rendered outline（`reports.py` L88-96），title 不进任何产物；从生成到导出（`mindmap.py` L262-264 只补"至少一个 #"、不保证唯一根、不校验根==title）三层都没有校验。→ 影响：导图根节点可能漂移为 LLM 任意写的标题或兜底"# 思维导图"，title 字段纯属浪费。→ 改进方向：渲染后程序校验/强制根标题 = title（或删掉 title 字段）。

- **[中] 渲染是"二次 LLM 改写"且无模板时温度不固定，存在漂移风险**：`steps/mindmap_render.py` L28-32 无模板时 `temperature=None`（用客户端默认，可能 >0），而渲染职责是"只规范化、不增删事实"（`prompts.py` L158）；渲染结果直接成为最终产物（HTML/PNG 导出源），没有任何"渲染后与已批准草稿结构等价"的校验。→ 影响：审核通过的草稿可能在渲染环节被重排/改写，审核结论失去意义。→ 改进方向：无模板时固定 temperature=0.0，或改为确定性程序化规范化（参照 minutes_trace 程序落钉思路）。

- **[中] markmap 依赖点脆弱：唯一根与层级连续性无强制**：prompt 只约束"最多 4 层"（`prompts.py` L30），sanitize 只在"完全没有 `#`"时补根（`mindmap.py` L262-264）；LLM 若输出两个 `#`（两个根）或先 `##` 后 `#`，markmap 的树结构行为不可控，而"标题层级不连续"类问题被 supervisor 的"结构失控"标准覆盖但无机械判定。→ 影响：极端输出下导图根/层级错乱，且用户不可见原因。→ 改进方向：导出前做确定性树校验（唯一根 + 层级连续），失败时回退纯文本大纲并在日志/质量警告中说明。

- **[低] 降级拼装绕过 sanitize**：`contracts.py` L52-53 `Raw("outline")` 直接用草稿 outline，若草稿含表格/超长节点（LLM 违反禁令），降级文本直接展示未清理内容，与导出路径（先 sanitize）质量不一致。→ 改进方向：fallback 前过 `sanitize_mindmap_outline`。

- **[低] "3–6 个主分支/禁止空分支"只有 prompt 承诺**：`prompts.py` L46、L53 的数量与空分支规则没有任何统计校验，supervisor 只拦"层级结构明显失实"。→ 改进方向：渲染或导出时统计主分支数，偏离过远仅记日志，不阻塞。

### 亮点（可选）

- 表格禁令是"prompt 硬性 + 渲染禁止 + 导出侧 sanitize 表格转短叶 + 公共前缀上提（`tools/mindmap.py` L75-178、L445-466）"三层防线，是三条线里程序硬约束最完整的一处；前缀上提规则配了正反例（`prompts.py` L61-94），指令可执行性强。

## 2. minutes_trace（溯源纪要）

### 问题清单

- **[中] 【场景模板包】注入是死路径，模板定制功能名存实亡**：`extras.py` L10 解析【场景模板包】块、`scene.py` L173-184 解析三引号赋值，但全仓库没有任何代码把 `samples/meeting/template.txt`/`test/template.txt` 注入 shared_context；runner 还显式跳过 minutes_trace 的 `--template`/`--mode` 参数（`runner.py` L94-110）。→ 影响：`common_meeting_requirement`/`GLOBAL_CONSTRAINT`/`conference_scenario_filtering` 全部失效，`scene_spec` 永远走默认骨架，用户自定义场景模板能力为空转。→ 改进方向：接入 runner/web 的模板上传并写入【场景模板包】块，或删除整套死代码并更新 docstring。

- **[中] 场景判定对整篇原文做关键词启发式，误判面大**：`scene.py` L211-226 优先级最高的一组是"评审/决策/决议/通过/不通过/风险/阻塞"，任何例会里出现"这个风险要关注"即判"项目决策与评审"；且与 meeting_core 内部判定的 scene 没有通道（见 0 节问题 1）。→ 影响：正文骨架（侧重、结论子节）与真实场景不符。→ 改进方向：场景判定收敛到理解层输出，或限定启发式作用范围（仅 purpose/原文头部）。

- **[中] 对齐的 evidence 字段完全无校验，且补挂条目 evidence 为空**：`gate_alignments`（`align.py` L197-215）校验了 sentence 存在于 minutes_md、source 能匹配用户关键点/笔记，但 evidence（契约要求"能对上会议原文的一句依据"，`contracts.py` L39）从不检查是否在 transcript 中——LLM 可编造一句"原文依据"顺利过门禁；`backfill_alignments` 补挂的条目 evidence 直接置空串（`align.py` L300、L320），与契约语义矛盾。→ 影响：溯源钉的证据可信度无保障（渲染虽只用 source，但数据结构上是假的）。→ 改进方向：校验 evidence 必须能在 transcript 中模糊匹配，否则置空或丢弃。

- **[中] stamp_minutes 全量 replace + 子串碰撞，会产生重复钉/错位钉**：`align.py` L348-349 `text.replace(sent, sent.rstrip() + suffix)` 会替换 minutes_md 中该句的**所有**出现处；若某句是另一句的子串（如"下周完成验收" vs"下周完成验收且提交报告"），先钉的 tag 会插进后一句内部，后一句再被钉一次。→ 影响：重复钉、钉进句中。→ 改进方向：按行逐行定位精确匹配，子串场景取最长句优先。

- **[中] reorg（重排）调用丢失场景与格式约束**：返工用户消息只有 REORG_PROMPT + 原因 + 称呼禁令 + 当前草稿（`minutes_trace_agent.py` L142-148），没有【写作要求】/【输出格式】/【重点覆盖清单】；而系统 prompt 第一句要求"严格遵循用户消息里给出的写作要求与输出格式"（`prompts.py` L16），REORG_PROMPT 也只字未提"内容总结/固定大标题"结构。→ 影响：返工稿可能丢掉场景骨架、固定标题集甚至内容总结段，返工反而劣化。→ 改进方向：reorg 用户消息复用 `scene_spec` 的 requirement/fmt 与 focus 指南。

- **[低] 系统 prompt 与场景化写作要求自相矛盾**：`prompts.py` L6"按通用会议纪要骨架写正文。不要猜测会议场景"与用户消息注入的场景化【写作要求】（`minutes_trace_agent.py` L113-115）并存——通用 vs 场景化两份指令，模型无所适从。→ 改进方向：首句改为"按用户消息中给出的写作要求组织"。

- **[低] 判人启发式把职务当人名**：`structure.py` L14 `[\u4e00-\u9fff]{1,3}(总|经理|老师|总监|主任)` 会把"总经理"（"总"+"经理"）这类纯职务收进 people 名单，`collect_people`（L18-38）又只排除"发言/speaker"开头；"总经理"进 banned 名单后，任何含"总经理"的议题标题都会被误判为"按人成章"触发 reorg。→ 改进方向：限定为"姓+职务"（2-3 字）并排除纯职务词。

- **[中] 附加材料双重注入 + 解析脆弱**：`line_extra` 已含【用户关键点/用户笔记】原文块（`runner.py` L208-215 → `domain_engine.py` L222-224），`_focus_guide`（`minutes_trace_agent.py` L32-52）又把同一批内容以"重点覆盖清单"格式注入一遍；`parse_notes`（`align.py` L16-26）只认 `->` 箭头，用户用 `→` 或中文冒号写的笔记被静默丢弃。→ 影响：token 浪费、两处口径不一致易让模型混淆；笔记格式脆。→ 改进方向：focus 只给归并指令不带原文；箭头解析兼容 `→`。

## 3. multi_styles（多样式纪要）

### 问题清单

- **[中] supervisor"先读「组织模式」"无对象，模式忠实度门禁失效**：`prompts.py` L288 要求审核时读「组织模式」行，但 `_supervisor_context`（`orchestrator.py` L339-359）从不注入 `line_modes`；supervisor 只能从草稿 `mode` 字段反推，若 LLM 生成 logic 内容却把 mode 写成 time，审核无从对照请求模式（且 mode 字段与 line_modes 无任何一致性校验）。→ 影响：请求模式与产出模式错位是静默的。→ 改进方向：把请求的组织模式注入 supervisor 上下文，并校验 draft.mode == line_modes 值。

- **[中] 三段阈值三处不一致**：生成 prompt 要求"尽量不少于 3 段"/urgency"≥3"（`prompts.py` L64、L267）；`enforce_multi_styles_sections` 只挡全空（`contracts.py` L76-77，1-2 段放行）；渲染 prompt 却"不足 3 段只输出 title+暂无结构化段落"（`prompts.py` L319）。→ 影响：1-2 段的有效草稿通过门禁却在渲染被丢弃，结构化数据（report.sections）与渲染文本互相矛盾。→ 改进方向：统一阈值（门禁与渲染一致），或渲染保留 1-2 段。

- **[中] causal 模式要求构建因果链，与"禁止编造"存在张力**：`prompts.py` L169 要求隐患必须"现状中的某事 → 若……则……"，本质是推导原文没有的因果传导句；`prompts.py` L33 又要求"事实锁定/禁止编造"。LLM 被夹在两者之间，supervisor 只拦"明显编造"。→ 影响：causal 模式幻觉风险显著高于其余四模式。→ 改进方向：把"若…则…"限定为原文已含的条件/依赖，推断句加"（推断）"标记，supervisor 增加对推断句可支持性的检查。

- **[中] 缺省模式静默回退到 logic**：`multi_styles_agent.py` L41-43 在 `_extract_mode` 取不到或取到非法值时静默使用 MODE_LOGIC_RULES，无日志、无 degraded 标记；`collect_modes`（`runner.py` L133-140）只做 lower 不校验枚举。→ 影响：line_modes 传递链路任何一环丢值，用户要 time 却拿到 logic 草稿且无人知晓。→ 改进方向：mode 缺失/非法时记 warning，或走显式空草稿而非静默换模式。

- **[中] 门禁清理与 prompt 规则重复且覆盖不全**：`enforce_multi_styles_sections` 的 `_strip_repeated_title`（`contracts.py` L53-59）只剥与自身 title 一致的重复前缀；错桶行（title="立即办理"、content 行首却是"限期完成：…"）无法清理，而 supervisor 明确"不拦截双冒号/分桶偏松"（`prompts.py` L294）。→ 影响：urgency 清单格式错误被设计性地放过并进入产物。→ 改进方向：enforce 对 urgency 模式做行级格式校验（识别五桶词表并剥离任意桶名前缀或报错）。

- **[低] 基础 prompt 超长且模式指纹自检与 supervisor 宽口径不匹配**：system prompt = 基础部分（五模式表格+铁律+指纹+五种写法示范，约 70 行）+ 单个模式规则块（约 50-80 行），`prompts.py` L47 要求"混入其他模式指纹必须重写"，但 supervisor"段内出现方面、时间词不全…一律通过"（L292-295）——段级串味无门禁。→ 影响：段内串味（time 段出现"方面"骨架）长期漏网。→ 改进方向：渲染阶段做指纹关键词扫描，命中记 soft 警告。

- **[低] 契约与 prompt 口径不一 + 文案不统一**：`contracts.py` L99"content 禁止用数组代替"与 `prompts.py` L28"content 优先用字符串；清单也可以写成多行文本"口径不一致，而 enforce（`contracts.py` L26-50）又防御性兼容数组；`contracts.py` L112 的 Feedback desc 是英文，与其它线中文文案不统一。→ 改进方向：统一为"content 必须是字符串"，enforce 只修不纵容；文案统一中文。

- **[低] line_modes 注入对所有线生效，接口语义不清**：`domain_engine.py` L219-221 对任意存在 line_modes 的线都前置"组织模式："行，而 runner 对除 minutes_trace 外的所有线都暴露 `--{line}_mode`（`runner.py` L94-110），mindmap/minutes_generation 会收到无意义行。→ 影响：接口暴露超出实际消费方，易误用。→ 改进方向：仅在 multi_styles 线注入，runner 也只对 multi_styles 暴露该参数。

## 总结

三条线最共性的薄弱点是"承诺型约束远多于机制型约束"：mode 忠实度、title=根标题、evidence 溯源、句级落钉、场景判定全部靠 prompt 自觉 + supervisor 宽口径（三条 supervisor 都是"犹豫→approve/只拦严重问题"），而 supervisor 上下文又普遍缺关键信息（multi_styles 缺组织模式、minutes_trace 缺用户关键点/笔记清单），审核退化为近似放行，返工环形同虚设。其次是大量"半成品/死路径"残留——场景模板包从未注入、mindmap title 死字段、multi_styles 的 ≥1/≥3 阈值三处打架、minutes_trace reorg 丢约束——说明迭代中层层加兜底但口径未收敛；下一步应优先统一"契约-上下文-门禁"三处的一致性，再把可机械判定的约束（根标题、evidence 溯源、桶名清洗、模式一致性）从 prompt 挪到程序层。
