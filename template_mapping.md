# 会议纪要模板对照表（cm_template_v2_changed_0722.yaml）

`template/` 下 29 个场景模板文件，按 YAML `template-ids` 值（`scenario_task` 下划线格式）命名。

| # | 文件名 | 中文名 | 场景 |
|---|---|---|---|
| 1 | `team_meeting.md` | 团队例会 | 会议 |
| 2 | `project_progress.md` | 项目进度会 | 会议 |
| 3 | `decision_review.md` | 决策评审会 | 会议 |
| 4 | `workshop_session.md` | 工作研讨会 | 会议 |
| 5 | `retrospective_session.md` | 总结复盘会 | 会议 |
| 6 | `exchange_forum.md` | 沟通交流会 | 会议 |
| 7 | `class_transcript.md` | 课堂记录 | 学习 |
| 8 | `special_lecture.md` | 专题讲座 | 学习 |
| 9 | `group_seminar.md` | 小组讨论 | 学习 |
| 10 | `knowledge_memo.md` | 知识笔记 | 学习 |
| 11 | `debate_forum.md` | 辩论会 | 学习 |
| 12 | `research_dialogue.md` | 调研访谈 | 访谈 |
| 13 | `interview_transcript.md` | 采访记录 | 访谈 |
| 14 | `hiring_report.md` | 面试报告 | 面试 |
| 15 | `interview_debrief.md` | 面试复盘 | 面试 |
| 16 | `clinical_advisory.md` | 就医咨询 | 医疗 |
| 17 | `psychological_session.md` | 心理咨询 | 医疗 |
| 18 | `legal_advisory.md` | 法律咨询 | 法律 |
| 19 | `court_transcript.md` | 庭审记录 | 法律 |
| 20 | `contract_vetting.md` | 合同审核 | 法律 |
| 21 | `media_briefing.md` | 新闻发布 | 发布 |
| 22 | `product_launch.md` | 产品发布 | 发布 |
| 23 | `government_bulletin.md` | 政府报告 | 发布 |
| 24 | `media_qa_session.md` | 媒体问答 | 发布 |
| 25 | `general_minutes.md` | 通用纪要 | 日常 |
| 26 | `personal_memo.md` | 个人备忘 | 日常 |
| 27 | `conversation_transcript.md` | 对话记录 | 日常 |
| 28 | `site_visit_tour.md` | 参观游览 | 日常 |
| 29 | `home_school_liaison.md` | 家校沟通 | 日常 |

## 场景分组速览

- **会议（6）**：team_meeting / project_progress / decision_review / workshop_session / retrospective_session / exchange_forum
- **学习（5）**：class_transcript / special_lecture / group_seminar / knowledge_memo / debate_forum
- **访谈（2）**：research_dialogue / interview_transcript
- **面试（2）**：hiring_report / interview_debrief
- **医疗（2）**：clinical_advisory / psychological_session
- **法律（3）**：legal_advisory / court_transcript / contract_vetting
- **发布（4）**：media_briefing / product_launch / government_bulletin / media_qa_session
- **日常（5）**：general_minutes / personal_memo / conversation_transcript / site_visit_tour / home_school_liaison

## 命名规则

取 `cm_template_v2_changed_0722.yaml` 中 `template-ids` 段的**值**（而非 key）：

```yaml
template-ids:
  meeting-minutes:        # key（连字符）
    team-meeting: team_meeting   # key: 值 → 文件名用值 team_meeting.md
```

格式：`scenario_task`（场景_任务），与 YAML 中 `id` / `default-template-id` 的引用值一致。
