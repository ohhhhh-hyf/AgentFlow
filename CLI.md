# CLI 运行命令

入口：`python bootstrap.py`。必须带 `--task`。在项目根目录执行。

默认画像是 `samples/<domain>/profile/object_profile.json`（客观全员）。  
产物写到 `output/<domain>/<task>/`。

---

## 公共参数

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--domain` | 否 | `meeting` 或 `notes`。不写则按解析顺序，建议显式指定 |
| `--task` | 是 | 任务线名或中文名。可重复，一次跑多条线 |
| `--file` | 否 | 输入文件或目录，可重复。资料入库可一次传多份；其它任务仍用第一个文件。默认 `samples/<domain>/file` |
| `--profile` | 否 | 用户画像 JSON。默认 `object_profile.json`（客观全员）。真人用 `personal_profile.json`；职业模板如 `client_manager_profile.json` / `product_manager_profile.json` / `project_manager_profile.json` / `developer_profile.json` |
| `--env` | 否 | 环境变量文件。默认项目根 `.env` |
| `--user_id` | 否 | 开启记忆 |
| `--project` | 否 | 会议域项目 ID；笔记域未传 `--subject` 时可当学科名 |
| `--subject` | 否 | 笔记记忆学科；自测题也可用来对齐科目 |
| `--chapter` / `--level` / `--grade` / `--edition` | 否 | 已弃用。自测题水平固定期中备考；年级和课本版本由笔记对齐知识点后反推 |
| `--difficulty` / `--qtype` | 否 | 自测题搜高中真题：难度、题型（可选） |
| `--<task>_template` | 否 | 该线渲染模板（`.md` / `.txt`），占位符 `[描述]` |
| `--<task>_mode` | 否 | 该线组织模式。目前只有 `multi_styles` 生效 |

`--task` 可用英文线名，也可用 `domain_config.py` 里的中文名。会议域额外别名：`minutes` → 纪要，`actions` → 待办，`trace` / `溯源纪要` → 溯源纪要。

---

## meeting（会议）

样例原文：`samples/meeting/file/seq_one.txt`  
溯源纪要推荐：`test/input`（同目录带 `user_keypoints.txt` / `user_notes.txt` / `template.txt`）

### 纪要 `minutes_generation`

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task minutes_generation
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task 纪要
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task minutes
```

可选渲染模板、记忆：

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task minutes_generation --minutes_generation_template samples/meeting/minutes_generation_template/simple_minutes.md --user_id u1 --project p1
```

### 待办 `action_items`

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task action_items
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task 待办
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task actions
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task action_items --action_items_template samples/meeting/action_items_template/action_items.md
```

### 风险分析 `risk`

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task risk
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task 风险分析
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task risk --risk_template path/to/risk.md --user_id u1 --project p1
```

### 思维导图 `mindmap`

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task mindmap
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task 思维导图
```

默认出 HTML。要 PNG 需本机：`pip install playwright` 且 `playwright install chromium`。

### 多样式纪要 `multi_styles`

组织模式 `--multi_styles_mode`：`time` / `logic` / `causal` / `party` / `urgency`。

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task multi_styles
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task 多样式纪要
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task multi_styles --multi_styles_mode time
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task multi_styles --multi_styles_mode logic
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task multi_styles --multi_styles_mode causal
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task multi_styles --multi_styles_mode party
```

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task multi_styles --multi_styles_mode urgency
```

### 溯源纪要 `minutes_trace`

`--file` 传目录时，会在同级查找 `user_keypoints.txt` / `user_notes.txt` / `template.txt`（也认 `keypoints.txt` / `notes.txt`）。缺省文件对应项为空。  
`--minutes_trace_template` 是最终渲染版式，和目录里的纪要骨架 `template.txt` 不是同一份。

```text
python bootstrap.py --domain meeting --file test/input --task minutes_trace
```

```text
python bootstrap.py --domain meeting --file test/input --task 溯源纪要
```

```text
python bootstrap.py --domain meeting --file test/input --task trace
```

```text
python bootstrap.py --domain meeting --file samples/meeting/input --task minutes_trace
```

指定单文件（仍会在该文件所在目录和 `test/`、`samples/meeting/` 里找旁路材料）：

```text
python bootstrap.py --domain meeting --file test/input/meeting.txt --task minutes_trace
```

---

## notes（笔记）

样例原文：`samples/notes/file/seq_one.txt`  
更长一份：`samples/notes/file/student_math_notes.txt`

记忆按 `--user_id` + `--subject`（未传 `--subject` 时可用 `--project` 当学科名）。

### 知识图谱 `knowledge_graph`

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task knowledge_graph
```

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task 知识图谱
```

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task knowledge_graph --user_id stu1 --subject 数学
```

同一 `user_id + subject` 再跑会增量合并图谱。

### 笔记审查 `review`

```text
python bootstrap.py --domain notes --file samples/notes/file/student_math_notes.txt --task review
```

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task 笔记审查
```

输出：带批注对照页 Markdown（`result_*.md`，给前端渲染）+ 订正笔记 Markdown（`result_*_corrected.md`，默认不展示，用户同意后才采用）。

### 自测题 `quiz`

```text
python bootstrap.py --domain notes --file samples/notes/file/student_math_notes.txt --task quiz
```

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task 自测题 --difficulty 适中 --qtype 单选题
```

水平固定为期中备考。学科、年级、课本版本由笔记对齐到的知识点反推，不用手填。难度 / 题型可选，用来在高中题库搜相关真题。答案和解析默认折叠。

```text
python bootstrap.py --domain notes --file samples/notes/file/student_math_notes.txt --task quiz --difficulty 适中 --qtype 单选题
```

### 资料入库 `library`

```text
python bootstrap.py --domain notes --file a.pptx --file b.pdf --file notes.txt --task library --user_id demo_user --subject gaoshu_limit
```

课件/讲义当资料骨架，文件名含「笔记」当学生笔记，含 teacher/划重点 的不当骨架。

### 知识目录 `catalog`

```text
python bootstrap.py --domain notes --task catalog --user_id demo_user --subject gaoshu_limit --file demo/teacher_focus_limits.txt
```

```text
python bootstrap.py --domain notes --task catalog --user_id demo_user --subject gaoshu_limit
```

从已入库资料生成四层目录（章节→主题→知识点→知识项）。`--file` 可选，传老师划重点文本用来标重点；不传也能出目录。同一 `user_id + subject` 再跑会基于已保存目录做增量更新，旧节点 ID 不变。

### 复习清单 `checklist`

```text
python bootstrap.py --domain notes --task checklist --user_id demo_user --subject gaoshu_limit --file demo/teacher_focus_limits.txt
```

基于已生成的 Knowledge Catalog 和本次老师划重点文本生成复习清单。必须先跑过 `catalog`。`--file` 是老师重点原文；不改长期目录，也不新建知识点。

```text
python bootstrap.py --domain notes --file samples/notes/file --task 资料入库
```

一次收多份文件或一个文件夹，写入同一知识库，并输出信息熵报告。不用指定 collection。跑完以后，同一库可供 `catalog` / `checklist` / `review` / `quiz` / `last_class` 引用。

---

## 一次跑多条任务

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task minutes_generation --task action_items --task risk
```

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task knowledge_graph --task review
```

---

## 个人视角

默认客观。要按人裁剪时显式传个人画像：

```text
python bootstrap.py --domain meeting --file samples/meeting/file/seq_one.txt --task minutes_generation --profile samples/meeting/profile/personal_profile.json
```

```text
python bootstrap.py --domain notes --file samples/notes/file/seq_one.txt --task knowledge_graph --profile samples/notes/profile/personal_profile.json
```

---

## 查看帮助

先指定领域，再看该域可用任务和模板/模式参数：

```text
python bootstrap.py --domain meeting --help
```

```text
python bootstrap.py --domain notes --help
```
