# 会议记忆（Memory）重构方案 v2.0 — 基于议题树的精准记忆体系

> **面向模块**：`domains/meeting/memory/`、`domains/meeting/tasks/minutes/`  
> **核心目标**：利用 `meeting_understanding` 议题树消灭记忆子系统的三个硬伤（扁平化、正则猜词、全局盲扫），同时保持所有任务线零影响。

---

## 一、现状：三个硬伤

### 1.1 extract.py 扁平化

`extract_meeting_fact()` 遍历 `topics` 时把 decisions/actions/risks/open_issues 全部拍平成顶级 `list[str]`。条目与 `module`（业务模块）、`title`（议题主题）彻底解绑。

**后果**：存储层变成无序散装短句，后续所有环节都在为"这条到底属于哪个议题"做补救。

### 1.2 inject.py 正则猜词

`_topic_label()` 用 `_LATIN_TERM` 和 `_NUM_UNIT_RE` 从条目文本中逆向猜主题名。

**后果**：从"内部专项标注还差400min"猜出 `400min`；从"端侧大概什么时候带上版本"猜出 `端侧`。生成的演进卡片标题荒诞。

### 1.3 render.py 全局盲扫

`apply_memory_citations()` 用 4~6 字 n-gram 在整篇正文自上而下贪婪搜索。

**后果**：第 1 场"鉴权网关时延指标"的历史摘录因命中"时延指标"4 字被错误锚定到第 2 场"前端渲染"段落。张冠李戴。

### 1.4 根因

三个硬伤的根因是同一个：**extract 阶段丢掉了议题结构，后续所有环节只能用启发式补救**。议题树（`meeting_understanding.topics`）本身已经把 module/title/decisions/actions/risks/open_issues 封装得很好，但记忆系统完全没用。

---

## 二、改造目标

```
改造前：
  topics → extract(拍平) → flat strings → state(全局模糊匹配)
         → inject(_topic_label 正则猜) → render(全局 n-gram 盲扫)

改造后：
  topics → extract(保留议题结构) → topic-scoped items
         → state(同 module 内匹配) → inject(原生 module/title)
         → render(按议题章节限定候选池)
```

**不改什么**：
- 不改 minutes_trace / actions / risks / agenda_minutes / consensus_decision / mindmap 的任何逻辑
- 不改 `meeting_understanding` 的 prompt 和输出契约
- 不改 `enforce_minutes_draft` 的搬运硬对齐逻辑
- 不改 `MINUTES_GENERATION_SYSTEM_PROMPT` 的核心结构（不加新规则）

---

## 三、分阶段改造（按 ROI 排序）

### 阶段一：extract.py — 保留议题结构（基础设施，一切的前提）

**改什么**：

`MeetingFact` dataclass 新增 `topics` 字段：

```python
@dataclass
class MeetingFact:
    # ... 现有字段保留 ...
    topics: list[dict[str, Any]] = field(default_factory=list)  # 新增
```

`extract_meeting_fact()` 改造：

```python
def extract_meeting_fact(understanding, transcript, ...):
    # 现有的 flat 提取逻辑完全保留（向后兼容）
    decisions = []
    risks = []
    # ... 现有遍历 topics 拍平的代码不动 ...

    # 新增：同时保留结构化议题
    topic_facts = []
    for t in (understanding.get("topics") or []):
        if not isinstance(t, dict):
            continue
        topic_facts.append({
            "topic_id": t.get("topic_id") or "",
            "module": t.get("module") or "",
            "title": t.get("title") or "",
            "decisions": [str(d).strip() for d in (t.get("decisions") or []) if str(d).strip()],
            "actions": [
                {
                    "text": a.get("task") or "",
                    "owner": a.get("owner") or "",
                    "timing": a.get("deadline") or "",
                    "deliverable": a.get("deliverable") or "",
                }
                for a in (t.get("actions") or [])
                if isinstance(a, dict) and (a.get("task") or "").strip()
            ],
            "risks": [
                r.get("risk") if isinstance(r, dict) else str(r)
                for r in (t.get("risks") or [])
                if (isinstance(r, dict) and r.get("risk")) or (isinstance(r, str) and r.strip())
            ],
            "open_issues": [str(o).strip() for o in (t.get("open_issues") or []) if str(o).strip()],
        })

    fact.topics = topic_facts
    return fact
```

**向后兼容**：
- `decisions`/`risks`/`open_items`/`action_items` 这些 flat 字段照旧产出
- `topics` 为空列表时不影响任何现有逻辑
- `meetings.jsonl` 旧数据没有 `topics` 字段 → `MeetingFact.from_dict` 默认 `[]`

**工作量**：小（~50 行改动）。**风险**：极低。

---

### 阶段二：inject.py — 废弃正则猜词（立即止血）

**改什么**：

`_topic_label()` 函数目前的逻辑是从条目文本中用正则"猜"主题名。改造后：

1. state.py 存储的每条 item 原生携带 `module` 和 `topic_title`
2. inject.py 直接读 `item["module"]` 和 `item["topic_title"]`，不再猜

```python
# 改造前（inject.py L147-183）
def _topic_label(text: str, anchors: list[str]) -> str:
    # 60 行正则启发式代码...

# 改造后
def _topic_label_v2(item: dict) -> str:
    """条目主题名：直接读原生字段，不猜。"""
    module = (item.get("module") or "").strip()
    title = (item.get("topic_title") or "").strip()
    if module and title:
        return f"{module}·{title}"
    return module or title or ""
```

`preview_comparison()` 和 `build_memory_context()` 中所有调用 `_topic_label(text, anchors)` 的地方改为 `_topic_label_v2(item)`。

**向后兼容**：旧 state 数据没有 `module`/`topic_title` → `_topic_label_v2` 返回空串 → 行为等价于现在猜不出来的情况（保持原格式，不硬凑主题）。

**工作量**：小（~30 行改动 + 删除 60 行正则代码）。**风险**：极低。

---

### 阶段三：state.py — 议题作用域匹配（精准化）

**改什么**：

`update_state()` 当前用全局 `similar()` 做条目匹配。改造为两层：

```python
def _scoped_match(new_item, history_items, threshold=0.6):
    """先按 module 初筛，再做条目相似度匹配。"""
    new_module = (new_item.get("module") or "").strip()

    # 第一层：module 重合度过滤
    if new_module:
        # module 不是精确相等，用 2-gram 覆盖率
        candidates = [
            h for h in history_items
            if _module_overlap(new_module, h.get("module") or "") > 0.4
        ]
        # 有 module 候选 → 只在候选内匹配
        if candidates:
            return _best_match(new_item, candidates, threshold)

    # 兜底：无 module 或候选为空 → 回退全局匹配（兼容旧数据）
    return _best_match(new_item, history_items, threshold)

def _module_overlap(a: str, b: str, n: int = 2) -> float:
    """两个 module 名的 n-gram 重合率。"""
    if not a or not b:
        return 0.0
    ga = {a[i:i+n] for i in range(len(a) - n + 1)} if len(a) >= n else {a}
    gb = {b[i:i+n] for i in range(len(b) - n + 1)} if len(b) >= n else {b}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))
```

**写入时携带 module/topic_title**：

在 `_upsert_open` / `_upsert_decisions` / `_upsert_risks` 中，新条目创建时从 fact.topics 中找到对应的 module 和 topic_title 写入：

```python
def _find_topic_for_item(text, topics):
    """从议题树中找到包含该条目的议题，返回 (module, topic_title)。"""
    for t in topics:
        all_texts = (
            t.get("decisions", []) +
            [a.get("text", "") for a in t.get("actions", [])] +
            t.get("risks", []) +
            t.get("open_issues", [])
        )
        if any(similar(text, s) > 0.7 for s in all_texts):
            return t.get("module", ""), t.get("title", "")
    return "", ""
```

**关键设计决策**：

> **module 匹配用模糊重合、不用精确相等。** 第 1 场叫"网关核心架构"，第 2 场叫"网关鉴权优化"，2-gram 重合率 > 0.4（共享"网关"），不会被误过滤。第 1 场的"日志模块"和第 2 场的"网关鉴权"，2-gram 重合率 ≈ 0，被正确隔离。
>
> **topic_title 不作硬过滤。** 每场会议的议题标题几乎不会重复出现（"鉴权方案选型" vs "鉴权压测复盘"），只作为辅助相关度信号，不作为过滤门槛。

**向后兼容**：旧 state 数据的条目没有 `module` → 走全局匹配兜底 → 行为与改造前完全一致。

**工作量**：中等（~100 行改动）。**风险**：中等。需要用多场会议数据验证 module 匹配不会误过滤。

---

### 阶段四：render.py — 作用域锚定（消灭张冠李戴）

**改什么**：

`apply_memory_citations()` 当前是全局 n-gram 扫描。改造为按议题章节限定候选池。

**实施分两步**：

**Step 1：先在 minutes_trace 上做（正文结构最确定）**

minutes_trace 的正文严格按 `## [议题名称]` 分章。分段是确定性的：

```python
def _split_by_sections(markdown: str) -> list[tuple[str, str]]:
    """按 ## 标题拆分 markdown，返回 [(section_title, section_content), ...]"""
    sections = []
    current_title, current_lines = "", []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current_title or current_lines:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_title or current_lines:
        sections.append((current_title, "\n".join(current_lines)))
    return sections
```

每个 section 只匹配 module/topic_title 与该 section 标题相关的历史条目：

```python
def apply_memory_citations_scoped(text, memory_items, ...):
    sections = _split_by_sections(text)
    for section_title, section_content in sections:
        # 只取与本 section 相关的历史条目
        scoped_items = [
            item for item in memory_items
            if _module_overlap(item.get("topic_title", ""), section_title) > 0.3
            or _module_overlap(item.get("module", ""), section_title) > 0.3
        ]
        # 在 section_content 内做 n-gram 匹配（限定范围）
        _apply_citations_in_section(section_content, scoped_items, ...)
```

**Step 2：推广到 minutes / minutes_styles**

这两条线的正文不一定有清晰的 `##` 标题。需要用会议理解的 topic titles 做模糊段落归属。这一步可以在 Step 1 验证效果后再做。

**工作量**：Step 1 中等（~80 行），Step 2 较大（~150 行）。  
**风险**：Step 1 低（minutes_trace 结构确定），Step 2 中等（段落归属可能不准）。

---

### 阶段五：存储格式升级

#### meetings.jsonl

在现有 flat 字段基础上追加 `topics` 数组。旧数据缺失 `topics` 时 `MeetingFact.from_dict` 返回 `[]`。

```json
{
  "meeting_id": "m_20261003_001",
  "title": "网关鉴权改造评审",
  "decisions": ["采用二级缓存方案"],
  "risks": ["多实例缓存不一致"],
  "topics": [
    {
      "topic_id": "T1",
      "module": "网关核心架构",
      "title": "鉴权方案选型与延迟优化",
      "decisions": ["采用二级缓存方案"],
      "actions": [{"text": "完成缓存保护设计", "owner": "李工", "timing": "10-10"}],
      "risks": ["多实例缓存不一致"],
      "open_issues": ["主从切换降级策略未定"]
    }
  ]
}
```

#### states/{project_id}.json

每条 item 新增 `module` 和 `topic_title`：

```json
{
  "item_id": "a1",
  "module": "网关核心架构",
  "topic_title": "鉴权方案选型与延迟优化",
  "text": "完成缓存保护设计",
  "status": "open",
  "owner": "李工"
}
```

旧 state 文件缺失 `module`/`topic_title` → 按空串处理 → 走全局匹配兜底。

#### registry.json

回写时把议题树的 `module` 列表加入项目 anchors（去重）。下一场会议的议题树出现相同 module 时可以毫秒级自动绑定。

---

## 四、Prompt 协调策略：不加规则，靠结构化注入

**核心原则**：当前 `MINUTES_GENERATION_SYSTEM_PROMPT` 已经 2000+ token、极度密集。不在 system prompt 里加新规则。

改造手段是优化 `build_memory_context()` 输出的结构化文本，让 LLM "照搬"而非"理解规则后执行"：

### 改造前（inject 输出）

```
【会议记忆】
【延续事项】
- 缓存保护设计（第1场·2026-09-25起，状态 open，负责人 李工）
  原文摘录：李工承诺下周五前输出...
【已闭环】
- 本地缓存时延基线（第1场关闭）
```

### 改造后

```
【会议记忆】
项目：网关架构改造（第2场，前序：第1场·2026-09-25）

【历史对照素材（草稿 history_comparison 请原样采纳）】
- 延续事项（网关核心架构·鉴权方案｜自第1场）：缓存保护设计待完成（负责人 李工）
- 已闭环（网关核心架构·鉴权方案｜第1场提出）：本地缓存时延基线确立
- 风险演变（网关核心架构·鉴权方案｜持续，自第1场）：多实例缓存数据不一致
- 合计：延续 1、闭环 1、风险 1

【历史决策（仅作背景，不是新决策）】
- 第1场：弃用 Zuul 迁移 Spring Cloud Gateway
```

改动点：
1. 每条对照项的括号里带 `module·title`（来自 item 原生字段，不再猜）
2. `history_comparison` 由 `core/graph/nodes.py:545` 确定性覆盖（现有机制不变）
3. 不在 system prompt 加规则——LLM 看到"请原样采纳"就够了

---

## 五、被排除在外的议题：Supervisor 与理解层瘦身

以下两个优化方向与记忆重构无关，但对整体性能有显著影响。记录在此供后续独立评估。

### 5.1 Supervisor 条件性跳过

**现状**：每条任务线都必经 `agent → supervisor → (revision) → render`。Supervisor 的 input 比 agent 还长（多一份草稿），且系统已经不得不加了两个 band-aid：
- `soften_unreasoned_reject`：无理由 reject → 降为 approve
- `soften_unsubstantial_revise`：全 pass 的 revise → 降为 approve

这说明 Supervisor 的误判率不低，系统在程序层面已经在"纠正 Supervisor 的纠正"。

**建议方向**：
- 短会（原文 < 2000 字）直接跳过 Supervisor
- 搬运字段已被 `enforce_minutes_draft` 程序对齐，Supervisor 对这部分的审核是冗余的
- 把关键检查（事实捏造）做成程序化规则（检查草稿中的人名是否在 speakers 列表中、数字是否在原文中出现），替代 LLM 审核

### 5.2 理解层 context_and_debate 瘦身

**现状**：`context_and_debate` 要求"100~200字自然连贯叙事"，但 minutes_agent 拿到它之后又要"把索引写开成自然段"——两个 LLM 在做高度重叠的叙事工作。

**建议方向**：
- 把 `context_and_debate` 改为 `context_gist`：只保留关键结论、数字、分歧点（30~60字），不要求叙事
- 减少理解层的 output token（当前这个字段占理解输出的 40%+）
- 让 minutes_agent 有更大的叙事空间——它有原文，不需要理解层帮它写好

---

## 六、风险清单与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|----------|
| 跨场次 module 命名不一致（"网关核心架构" vs "网关鉴权优化"） | 高 | 用 2-gram 重合率而非精确匹配；保留全局匹配兜底 |
| 旧 meetings.jsonl 无 topics 字段 | 低 | `from_dict` 默认空列表；所有消费方检查 `if topics` |
| minutes/minutes_styles 正文无清晰章节标题 | 中 | 作用域锚定先在 minutes_trace 上做；其他线暂保留全局匹配 |
| 注入文本变长导致 LLM 上下文膨胀 | 低 | 改造后的注入比改造前更紧凑（带结构 vs 散装句子） |
| rebuild_state 在大量历史会议下变慢 | 低 | module 初筛减少了比对次数，性能应该更好 |

---

## 七、验收标准

1. **extract**：`MeetingFact.topics` 非空且与 `meeting_understanding.topics` 结构一致；flat 列表字段值不变
2. **inject**：对照行的括号内出现 `module·title`，不再出现 `400min`、`端侧` 等畸形标签
3. **state**：同 module 内的跨场条目能正确匹配延续/闭环；不同 module 的同名条目不会误配
4. **render**（minutes_trace）：历史证据卡片只出现在与其 module 相关的议题章节旁，不再跨章节乱标
5. **零回归**：所有现有单测通过；actions/risks/minutes_trace/agenda_minutes/consensus_decision 的输出不变
