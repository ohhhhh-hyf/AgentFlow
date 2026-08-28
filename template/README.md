# 模板注册表（8 场景 29 类）

模板的权威来源是根目录 **`cm_template_v2_changed_0722.yaml`**；本目录下的
`.md` 文件是各模板 `format`（占位符模板）的可读副本，文件名 = 模板 ID。
**新增/修改模板以 yaml 为准**，并同步本目录 md 副本。

## 1. 8 个场景

| 场景ID | 场景名 | 别名 |
|---|---|---|
| meeting_minutes | 会议 | 时间：记录时间：／地点：／参与人员： |
| study_notes | 学习 | 记录时间：／地点：／主讲人员： |
| dialogue_interview | 访谈 | 记录时间：／地点：／参与人员： |
| job_interview | 面试 | 记录时间：／地点：／参与人员： |
| medical_consultation | 医疗问诊 | 记录时间：／地点：／参与人员： |
| legal_consultation | 法律沟通 | 记录时间：／地点：／参与人员： |
| press_conference | 新闻发布 | 记录时间：／地点：／参与人员： |
| daily_journal | 日常记录 | 记录时间：／地点：／参与人员： |

## 2. 29 类模板（order = yaml 定义顺序；template 值 = API `extra.template`）

| order | 场景ID | 模板ID | 中文名 | 描述 | API `template` 值 |
|---|---|---|---|---|---|
| 1 | meeting_minutes | team_meeting | 团队例会 | 梳理团队进展 | `meeting_minutes_team_meeting` |
| 2 | meeting_minutes | project_progress | 项目进度会 | 追踪项目进度 | `meeting_minutes_project_progress` |
| 3 | meeting_minutes | decision_review | 决策评审会 | 记录评审结论 | `meeting_minutes_decision_review` |
| 4 | meeting_minutes | workshop_session | 工作研讨会 | 提炼研讨观点 | `meeting_minutes_workshop_session` |
| 5 | meeting_minutes | retrospective_session | 总结复盘会 | 内容总结复盘 | `meeting_minutes_retrospective_session` |
| 6 | meeting_minutes | exchange_forum | 沟通交流会 | 整理沟通结果 | `meeting_minutes_exchange_forum` |
| 7 | study_notes | class_transcript | 课堂记录 | 整理课堂重点 | `study_notes_class_transcript` |
| 8 | study_notes | special_lecture | 专题讲座 | 提炼讲座观点 | `study_notes_special_lecture` |
| 9 | study_notes | group_seminar | 小组讨论 | 归纳小组讨论 | `study_notes_group_seminar` |
| 10 | study_notes | knowledge_memo | 知识笔记 | 梳理知识框架 | `study_notes_knowledge_memo` |
| 11 | study_notes | debate_forum | 辩论会 | 还原辩论观点 | `study_notes_debate_forum` |
| 12 | dialogue_interview | research_dialogue | 调研访谈 | 总结调研内容 | `dialogue_interview_research_dialogue` |
| 13 | dialogue_interview | interview_transcript | 采访记录 | 整理采访观点 | `dialogue_interview_interview_transcript` |
| 14 | job_interview | hiring_report | 面试报告 | 评估候选人表现 | `job_interview_hiring_report` |
| 15 | job_interview | interview_debrief | 面试复盘 | 复盘个人表现 | `job_interview_interview_debrief` |
| 16 | medical_consultation | clinical_advisory | 就医咨询 | 整理就医过程 | `medical_consultation_clinical_advisory` |
| 17 | medical_consultation | psychological_session | 心理咨询 | 记录心理咨询 | `medical_consultation_psychological_session` |
| 18 | legal_consultation | legal_advisory | 法律咨询 | 梳理案件建议 | `legal_consultation_legal_advisory` |
| 19 | legal_consultation | court_transcript | 庭审记录 | 还原庭审过程 | `legal_consultation_court_transcript` |
| 20 | legal_consultation | contract_vetting | 合同审核 | 识别合同条款 | `legal_consultation_contract_vetting` |
| 21 | press_conference | media_briefing | 新闻发布 | 提炼新闻信息 | `press_conference_media_briefing` |
| 22 | press_conference | product_launch | 产品发布 | 整理产品卖点 | `press_conference_product_launch` |
| 23 | press_conference | government_bulletin | 政府报告 | 梳理政策目标 | `press_conference_government_bulletin` |
| 24 | press_conference | media_qa_session | 媒体问答 | 还原问答过程 | `press_conference_media_qa_session` |
| 25 | daily_journal | general_minutes | 通用纪要 | 适用所有录音摘要 | `daily_journal_general_minutes` |
| 26 | daily_journal | personal_memo | 个人备忘 | 整理个人备忘 | `daily_journal_personal_memo` |
| 27 | daily_journal | conversation_transcript | 对话记录 | 提炼对话内容 | `daily_journal_conversation_transcript` |
| 28 | daily_journal | site_visit_tour | 参观游览 | 记录参观过程 | `daily_journal_site_visit_tour` |
| 29 | daily_journal | home_school_liaison | 家校沟通 | 记录家校沟通 | `daily_journal_home_school_liaison` |

## 3. 特殊模板与默认值

| 项 | 值 | 说明 |
|---|---|---|
| 默认输出 | `""`（空字符串） | API 的 `extra.template` 缺省 / 空字符串 = **不套模板**，走各任务 prompt 的默认输出（如 minutes 的默认会议纪要）；29 类模板均需显式指定 |
| 用户自定义 | `user_customized` | yaml 预留，order 9999、visible=false，占位"用户自定义提示词" |

## 4. 已过期模板（yaml `expired-templates`）

| 过期 ID | 替代为 | 过期时间 |
|---|---|---|
| meeting_minutes | workshop_session | 2026-07 |
| dialogue_interview | interview_transcript | 2026-07 |
| study_notes | knowledge_memo | 2026-07 |
| intelligence_meeting_minutes | general_minutes | 2026-07 |

## 5. API 用法

```json
{
  "extra": {
    "template": "meeting_minutes_team_meeting"
  }
}
```

- 格式：`{场景ID}_{模板ID}`，非法值返回业务码 `40002`。
- **缺省 / 空字符串 = 不套模板**，走各任务 prompt 的默认输出；29 类模板均需显式指定。
- 模板文本取 yaml 的 `format` 字段；`template/*.md` 仅为可读副本。
