# tools/ 模块地图

与领域无关的运行时与导出工具。业务代码统一按子包导入
（`tools.schema.*` / `tools.core.*` / `tools.runtime.*` / `tools.exports.*` /
`tools.templates.*` / `tools.execution.*`），**不在 `tools/__init__.py` 做顶层 re-export**。

## 分层

| 包 | 模块 | 职责 |
|---|---|---|
| `schema/` | `contracts.py` | Generation / Supervisor 契约 DSL |
| | `fallback_rules.py` | 降级拼装规则 DSL |
| | `validation.py` | 结构化输出校验工具 |
| `core/` | `domain_engine.py` | 多 domain 共享 LangGraph 节点 / 流式生产（纯函数再导出自 `domain_engine_text`） |
| | `domain_engine_text.py` | 线状态、报告组装、降级拼装等纯函数 |
| | `runner.py` | 任务运行入口、done 后落盘/导出编排 |
| | `runtime_context.py` | `load_domain`、任务别名、环境默认路径 |
| | `io.py` | 样例路径解析、读 transcript / profile |
| | `profiles.py` | 用户画像共享目录与角色模板解析 |
| | `prompt_utils.py` | `build_render_prompt` 统一入口 |
| | `logging_config.py` | 日志初始化 |
| `execution/` | `hard_execution.py` | 上游硬对齐、表行截断、验收门禁 |
| `runtime/` | `render.py` | 图外 `produce_line` 渲染运行时 |
| | `context.py` | 渲染上下文（理解钩子） |
| | `kinds.py` | 任务线种类与策略解析（`LINE_KINDS`） |
| | `supervisor_slice.py` | 审核草稿压缩 |
| `templates/` | `template_prompt.py` | 模板渲染 system 规则拼装 |
| | `template_eval.py` | 通用约束评测、表格粘连修复 |
| `template_router/` | `_detect/_gate/_placeholder/_base` | 三类模板判型、门禁、占位填充 |
| `exports/` | `outputs.py` | 报告 JSON/Markdown 落盘 + mindmap/图谱导出编排 |
| | `knowledge_graph.py` | Graphviz SVG + 交互 HTML + 学习地图（notes.graph 用） |
| | `mindmap.py` | markmap HTML + Playwright PNG |
| | `consensus_decision.py` | 共识决策结构导出 |

## 可选子系统（独立使用，不绑死主流程）

| 路径 | 职责 |
|------|------|
| `memory/` | 项目记忆：原文实体挂钩；纪要对照历史；知识图谱增量合并 |
| `knowledge/` | 文档知识库：PPT/PDF 等入库、向量检索、问答带来源出处 |
| `meeting_memory/` | 会议记忆：项目核心名绑定、场次状态机、跨会引用与写回 |
| `ocr/` | OCR 引擎适配（serverocr / rapidocr / paddleocr）与版面清理 |
| `monitor/` | 任务监控：token / 缓存命中 / 按层耗时 |
| `exercise_search/` | 题库检索（notes.quiz 用） |
| `scripts/` | `register_task` / `sync_domain` 代码生成脚手架（开发期） |

## 约定

- **不要**在 `tools/` 引用具体 `domain.*` 任务实现（脚手架脚本除外）。
- 新增导出能力优先放在 `exports/outputs.py` 编排，具体渲染放独立模块。
- 渲染上下文与降级节点不再由 `sync_domain.py` 按线生成；领域只声明
  `_understanding_key` / `_transcript_label` / `_understanding_label`。
- 任务线种类写在 `domain_config.LINE_KINDS`（手写，见 `tools/runtime/kinds.py`）：
  `llm_extract` / `llm_document` / `deterministic_pipeline`（minutes_trace 即
  文档化的 pipeline + sidecar 线，新线用 `register_task.py --kind`）。
- 清理/重构时保持对外函数签名稳定，避免打断 domain 与调用方。
