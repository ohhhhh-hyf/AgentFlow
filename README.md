# 个性化会议纪要多 Agent 系统

基于 DeepSeek 的会议纪要/知识点多 Agent 系统：多任务线并行流水线
（会议纪要 / 待办 / 风险分析 / 思维导图 / 知识点），每条线独立执行
"生成 → 领域审核（+全局标准注入）→ 渲染"，互不阻塞；
支持客观视角与个人视角；可扩展任意新任务线。

## 项目结构

```
bootstrap.py                  # CLI 入口
domain/
  meeting/
    domain_config.py          # 领域配置：STATE_CLASS / LINE_CN_NAMES（中文名注册表）
    models.py                 # 数据模型 + 各线生成模型/审核模型（生成区）
    reports.py                # 全部任务线最终输出 Report 类（手写区）
    orchestrator.py           # 多线并行图 + 节点 + run/run_streaming
    meeting_factory.py        # Agent 依赖组装工厂
    meeting_core/             # 核心层：会议理解（客观事实底座）
    tasks/
      minutes_generation/     # 纪要线（contracts.py / prompts.py / steps/）
      action_items/           # 待办线（contracts.py / prompts.py / steps/）
      risk/                   # 风险分析线（contracts.py / prompts.py / steps/）
      mindmap/                # 思维导图线（大纲 → markmap HTML/PNG）
      ...                     # 新增任务线同构
      {line}/steps/           # agent / supervisor / render 三步骤实现
    samples/                  # 示例会议文本 / 用户画像 / 模板
  notes/                      # 笔记域：笔记理解 + 知识点总结（points 线）
perspective/                  # 跨 domain 公共视角建模（agent/模型/迷你生成器）
llm_client/                   # DeepSeek 客户端 + 配置（.env）
supervisor/                   # 全局监督标准（prompt 注入，不单独调 LLM）
schema_repair/                # 结构化输出修复（LLM 输出非法时）
tools/
  contracts.py                # 契约 DSL（GenerationContract / SupervisorContract）
  fallback_rules.py           # 降级拼装规则 DSL（Raw / Join / Lines）
  validation.py               # 输出校验工具
  prompt_utils.py / template_prompt.py   # 渲染 prompt 构建
  template_router.py          # 模板路由：占位符/格式规范/自然语言三类自动判型 + 编译
  mindmap.py                  # 思维导图导出：markmap-cli（HTML）+ Playwright（PNG）
  scripts/
    sync_domain.py                # 代码生成器：从契约生成模型/装配/骨架（--write/--check）
    register_task.py               # 新增任务线第一步：注册 + 骨架 + 工厂 import
```

## 快速开始

### 1. 环境准备

```bash
# Python >= 3.10，安装依赖
pip install -r requirements.txt
```

可选前置（按需）：

```bash
# 思维导图 HTML 导出需要 Node.js（npx 首次自动下载 markmap-cli，无需全局安装）
# 思维导图 PNG 导出还需要浏览器内核：
pip install playwright && playwright install chromium
```

### 2. 配置 API Key

在项目根目录创建 `.env`：

```
DEEPSEEK_API_KEY=sk-你的Key
```

可选配置（均有默认值）：

```
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.0
```

### 3. 运行

```bash
# 指定任务线（可多值）
python bootstrap.py --task minutes_generation --task action_items \
  --summary .\domain\meeting\samples\summary\meeting_all.txt \
  --profile .\domain\meeting\samples\profile\object_profile.json

# 思维导图：默认直接输出 PNG 图片到 output/（--mindmap-format png|html|both）
python bootstrap.py --task mindmap \
  --summary .\domain\meeting\samples\summary\meeting_all.txt \
  --profile .\domain\meeting\samples\profile\object_profile.json

# 笔记域：知识点总结
python bootstrap.py --domain notes --task points --summary .\domain\notes\samples\note.txt --profile <画像.json>
```

## 自定义输出模板

用 `--minutes_template` 指定纪要输出模板（`.md` 文件）。模板支持三种形式，系统**自动判型**处理：

| 形式 | 示例 | 处理方式 |
|---|---|---|
| **占位符模板** | `# [会议主题]` / `\| [任务] \| [负责人] \|` | 固定文字逐字符保留，LLM 只填占位符 |
| **格式规范模板** | 格式说明 + 输入/输出示例（如 JSON 数组） | 指令/示例分离，示例作 few-shot |
| **自然语言描述** | "第一行是标题，括号里跟时间和人物" | LLM 先编译成占位符模板再填充 |

```bash
python bootstrap.py --task minutes_generation --summary ... --profile ... \
  --minutes_template .\domain\meeting\samples\summary_template\simple_minutes.md
```

开关：环境变量 `TEMPLATE_ROUTER=off` 关闭模板路由，恢复旧行为。

## 新增任务线（如"风险管理"）

手写 4 处 + 命令 4 条（以线名 `xxx`、中文名 `xxx` 为例）：

```
① 手写 domain/meeting/tasks/xxx/contracts.py      # 生成/审核契约 + 降级规则
② python tools/scripts/register_task.py --domain meeting --task xxx --name "中文名"
   # 自动：注册中文名 + steps/ 三件套 + 工厂 import + 占位校验类
③ 手写 domain/meeting/tasks/xxx/prompts.py         # 4 个 prompt 常量
④ reports.py 末尾追加 XxxReport 类（继承 ModelMixin, XxxReportValidation）
⑤ python tools/scripts/sync_domain.py --domain meeting   # 全量生成 → SUCCESS!
⑥ python tools/scripts/sync_domain.py --domain meeting --check   # 校验 → SUCCESS!
⑦ python bootstrap.py --task xxx --summary ... --profile ...
```

## 架构要点

- **多线并行**：各任务线监督返工闭环（approve/revise≤1次/reject→降级），互不阻塞
- **契约驱动**：每条任务线的模型/校验/装配由 `contracts.py` 声明，`sync_domain.py` 生成
- **生成区**：`models.py` / `orchestrator.py` / `meeting_factory.py` 的生成区由脚本管理
  （`--write` 重写、`--check` 校验），手写区（contracts/prompts/reports 类）脚本不碰
- **全局标准注入**：`supervisor/` 的全局标准经 `GlobalSupervisor.build_prompt` 注入各线 supervisor
- **占位校验**：register 阶段预生成 `XxxReportValidation: pass`，写 Report 类无 NameError，
  sync_domain 全量后按字段生成真实校验
- **模板路由**：`tools/template_router.py` 自动判型三类模板并分派最优处理，
  任何失败回退旧路径；渲染输出附带只读校验（残留占位符/JSON 合法性）
- **思维导图**：mindmap 线产出 Markdown 大纲，经 `tools/mindmap.py` 导出
  交互式 HTML（markmap，离线单文件）或 PNG 图片（Playwright 截图）；
  `--mindmap-format` 默认 png，npx/playwright 缺失时自动降级不影响主流程
- **输出稳定性**：各线 prompt 采用确定性规则（数量由内容决定、措辞锚定原文、
  顺序按原文出现、空字段 null/[]），同一输入重复运行保持内容与篇幅稳定
