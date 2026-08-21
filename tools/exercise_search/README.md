# 题库检索 `tools/exercise_search`

把 `exercise_search_tool` 接到 AgentFlow：高中科目/版本/课本/知识点/题型用本地全量统计对齐，真正取题走 **`/bank/v1/question`**（带解析/答案/选项）。不要用旧的 `/v1/question`，那边大约八成题没有解析。

当前 demo 只覆盖**高中**。`notes.quiz` 在原有推理题之外调用本工具搜相关真题。

## 用法

```python
from tools.exercise_search import ExerciseSearchTool

bundle = ExerciseSearchTool().search_for_notes(
    notes_text,
    understanding=notes_understanding,   # 可选，用 key_terms / sections 对齐知识点
    subject="数学",                       # 不传则从笔记推断
    difficulty="适中",                    # 容易 / 较易 / 适中 / 较难 / 困难
    qtype="单选题",
)
```

科目和知识点从笔记对齐。年级、课本版本由命中的知识点反查课本章节得到，不必手填。难度、题型由调用方传入。

## 取题顺序

1. 用笔记对齐科目和知识点，再按课本章节反推年级 / 课本版本（`book_id` 用 /bank/ 的 textbook_id）
2. `GET /bank/v1/question`（`order=6`；先 `page=1` 不够再 `page=2`；难度传 4~8）
3. 丢掉没有解析或没有答案的题；知识点未命中则退到题干关键字

检索失败不会抛给 quiz，只留下说明。

## 凭据

读项目根 `.env`：

```
EXERCISE_SEARCH_APP=
EXERCISE_SEARCH_APP_SECRET=
EXERCISE_SEARCH_BASE=https://dnfyyds.tech/server1
EXERCISE_SEARCH_BANK_BASE=https://dnfyyds.tech/server1/bank
EXERCISE_SEARCH_ASSET_BASE=https://contres.readboy.com
```

题干/解析里的图片：`/resources/aixue_paper/...` 拼到 `https://contres.readboy.com` 后下载并内嵌；`/quesimg/` 走组卷 CDN。可用 `EXERCISE_SEARCH_ASSET_BASE` 覆盖图床。

缺省使用题库文档里的实测值。成功码是 `10000`，`page_size` 上限 20。取题走 `/bank/v1/question`，返回 `data.list`。
