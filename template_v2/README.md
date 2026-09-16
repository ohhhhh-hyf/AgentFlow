# template_v2（优化稿，供对比）

本目录是 `template/*.md` 的优化稿：逐字差异见 [DIFF.md](DIFF.md)，逐文件对比可 `diff -u template/xx.md template_v2/xx.md`。

- 优化范围：仅方括号内的内容提示与 1 处 requirement 措辞；
- 整体结构不动：标题、章节顺序、表格、占位符示例行全部保持原样；
- 生效方式：本目录**不被运行时读取**——`python tools/scripts/draft_template_v2.py --apply` 把 EDITS 写进权威 `cm_template_v2_changed_0722.yaml`（`templates[].format` / `requirement`），并刷新 `template/` 副本；
- 落地后的改动明细看 `git diff template/` 与 `git diff cm_template_v2_changed_0722.yaml`；
- 重新生成/校验：`python tools/scripts/draft_template_v2.py --write|--check`。

## 修改点与理由

### 2. 项目进度会（`meeting_minutes_project_progress`）

- **[format]** 进度会概况应落在「阶段 + 健康度」两条主线上（需求：聚焦项目健康度）
- **[format]** 补状态口径，避免同一份纪要里状态用词各异（不加字段、不增量）
- **[format]** 原文漏了「用…强调」，占位符说明不成句

### 3. 决策评审会（`meeting_minutes_decision_review`）

- **[format]** 与其他章节统一为「用 **…** 强调」的占位符口径

### 5. 总结复盘会（`meeting_minutes_retrospective_session`）

- **[format]** 复盘概况缺「目标 vs 结果」的对比（需求：还原预期目标与实际结果）
- **[format]** 错字与多余空格：需求要求归因到根本原因，措辞统一为「根因」

### 7. 课堂记录（`study_notes_class_transcript`）

- **[format]** 课程概况补课程名称/章节，便于日后检索复习
- **[format]** 作业与提交要求是可执行项，不应作为「也可列出」的补充

### 8. 专题讲座（`study_notes_special_lecture`）

- **[format]** 讲座概况补主讲人/机构（需求：专有名词须准确提取）
- **[format]** 同义反复压缩为一句，降低提示噪声（信息量不变）
- **[format]** 四句压成一句，保留「忠于原文语境 + 交代背景」两条硬要求

### 9. 小组讨论（`study_notes_group_seminar`）

- **[format]** 修正顿号病句，并补成员构成（小组讨论的必要背景）
- **[format]** 需求要求不遗漏关键发言，需能对应到人

### 10. 知识笔记（`study_notes_knowledge_memo`）

- **[format]** 串场景修正：知识笔记不是会议，「会议讨论/发言」改为知识域表述
- **[format]** 同上：会议 → 原文
- **[format]** 串场景修正 + 明确产出物是「核心结论」（与章节名一致）

### 11. 辩论会（`study_notes_debate_forum`）

- **[format]** 顿号病句（同小组讨论模板）
- **[format]** 直引号统一为书名号式引号，与其余模板标点一致

### 12. 调研访谈（`dialogue_interview_research_dialogue`）

- **[format]** 错字「忠实与原文」→「忠实于原文」；「倾向、表达」改为可执行的表述

### 13. 采访记录（`dialogue_interview_interview_transcript`）

- **[format]** 删掉内部变量名【待处理文本】（会泄漏到提示词），并拆清「记录/已确认/呈现方式」三层要求

### 14. 面试报告（`job_interview_hiring_report`）

- **[format]** 「面试过程中的具体内容」指向不明，改为可评估的「整体面试表现」
- **[format]** 面试报告缺结论项：补推进建议，避免只罗列观察

### 15. 面试复盘（`job_interview_interview_debrief`）

- **[format]** 多余空格
- **[format]** 改进计划补优先级，便于取舍

### 17. 心理咨询（`medical_consultation_psychological_session`）

- **[format]** 咨询概况补咨询目标，便于跨次咨询衔接
- **[format]** 补情绪变化与风险评估两条临床必要信息（仅在原文提及时记录，不编造）

### 19. 庭审记录（`legal_consultation_court_transcript`）

- **[format]** 错词：应为「争议焦点」（需求：聚焦争议焦点）
- **[format]** 原文仅 6 字，未宣判/调解场景会丢关键信息，按庭审实际情形补齐

### 20. 合同审核（`legal_consultation_contract_vetting`）

- **[format]** 顿号病句 + 「合同沟通」与审核场景不符
- **[format]** 合同审核的必要条款缺违约责任与争议解决（需求点名违约责任）

### 22. 产品发布（`press_conference_product_launch`）

- **[format]** 定位章节混入了演示/语录（应属佐证），改为明确「对比同类产品的差异化」
- **[format]** 写作技巧提示改为本条线最关键的准确性红线（参数与原文一致）

### 23. 政府报告（`press_conference_government_bulletin`）

- **[format]** 政府报告缺「报告期间」，指标口径无法定位
- **[format]** 领域改为随原文而定，避免预设报告不涉及的领域

### 25. 通用纪要（`daily_journal_general_minutes`）

- **[requirement]** 写作要求是半句病句（「目的为生成…和确保…」），改为可执行的祈使句，含义不变

## 未改动（现有措辞已准确、完整）

- 团队例会（`meeting_minutes_team_meeting`）、工作研讨会（`meeting_minutes_workshop_session`）、沟通交流会（`meeting_minutes_exchange_forum`）、就医咨询（`medical_consultation_clinical_advisory`）、法律咨询（`legal_consultation_legal_advisory`）、新闻发布（`press_conference_media_briefing`）、媒体问答（`press_conference_media_qa_session`）、个人备忘（`daily_journal_personal_memo`）、对话记录（`daily_journal_conversation_transcript`）、参观游览（`daily_journal_site_visit_tour`）、家校沟通（`daily_journal_home_school_liaison`）
