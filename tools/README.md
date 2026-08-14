# tools/ 模块地图

与领域无关的运行时与导出工具。业务代码统一 `from tools.xxx import ...`，**本包不在 `__init__.py` 做顶层 re-export**。

## 分层（第一刀）

旧导入路径保持不变。新代码按层落盘：

| 层 | 路径 | 职责 |
|---|---|---|
| 编排内核 | `runtime/` | 理解钩子、渲染上下文、图外 `produce_line`；`DomainNodes` 仍从 `domain_engine` 导入 |
| 应用 | `runner.py` / `runtime_context.py` / `io.py` | CLI、领域加载、读入 |
| 产物 | `outputs.py` | 报告落盘与导图编排 |
| 模板 | `template_router.py` | 判型 / 编译 / 评测 |
| 记忆 | `memory/` | 可选子系统 |

渲染上下文与降级节点不再由 `sync_domain.py` 按线生成。领域只声明 `_understanding_key` / `_transcript_label` / `_understanding_label`。

任务线种类写在 `domain_config.LINE_KINDS`（手写，见 `tools/runtime/kinds.py`）：

| 种类 | 代表线 | LLM 渲染 | CLI 模板 | sidecar | 结构抽取 |
|---|---|---|---|---|---|
| `llm_extract` | risk / points / action_items | 是 | 是 | 否 | 是 |
| `llm_document` | 纪要 / 多样式 / 思维导图 | 是 | 是 | 否 | 仅当 Report 声明 structure |
| `deterministic_pipeline` | minutes_trace；无模板 knowledge_graph | 默认否 | 默认否 | 可选 | 否 |

minutes_trace 是文档化的 pipeline + sidecar，不是和 risk 对等的一条 3-step 线。新线用 `register_task.py --kind`。

## 运行入口与 IO

| 模块 | 职责 |
|------|------|
| `runner.py` | CLI 参数、模板收集、调用 domain 图、done 后落盘/导出 |
| `runtime_context.py` | `load_domain`、任务别名、环境默认路径 |
| `io.py` | 样例路径解析、读 transcript / profile |
| `logging_config.py` | 日志初始化 |

## 编排内核

| 模块 | 职责 |
|------|------|
| `domain_engine.py` | 多 domain 共享 LangGraph 节点 / 流式生产；纯函数再导出自 `domain_engine_text` |
| `domain_engine_text.py` | 线状态、报告组装、降级拼装等纯函数 |
| `contracts.py` | Generation / Supervisor 契约 DSL |
| `fallback_rules.py` | 降级拼装规则 DSL |
| `validation.py` | 结构化输出校验工具 |

## 模板与强执行

| 模块 | 职责 |
|------|------|
| `template_router.py` | 三类模板判型、编译、占位符拼装填充 |
| `template_prompt.py` | 模板渲染 system 规则拼装 |
| `template_eval.py` | 通用约束评测、表格粘连修复 |
| `prompt_utils.py` | `build_render_prompt` 统一入口 |
| `hard_execution.py` | 上游硬对齐、表行截断、验收门禁 |

## 产物导出

| 模块 | 职责 |
|------|------|
| `outputs.py` | 报告 JSON/Markdown 落盘 + mindmap/图谱导出编排 |
| `mindmap.py` | markmap HTML + Playwright PNG |
| `knowledge_graph.py` | Graphviz SVG + 交互 HTML + 学习地图 |

## 可选子系统（独立使用，不绑死主流程）

| 路径 | 职责 |
|------|------|
| `memory/` | 项目记忆：原文实体挂钩；纪要对照历史；知识图谱增量合并 |
| `scripts/` | `register_domain` / `register_task` / `sync_domain` 脚手架（开发期） |

## 约定

- **不要**在 `tools/` 引用具体 `domain.*` 任务实现（脚手架脚本除外）。
- 新增导出能力优先放在 `outputs.py` 编排，具体渲染放独立模块。
- 清理/重构时保持对外函数签名稳定，避免打断 domain 与 Gradio。
