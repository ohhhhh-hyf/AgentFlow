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
  notes/                      # 笔记域：笔记理解 + 知识点（points）+ 知识图谱（knowledge_graph）
samples/                      # 终端参数对应的样例输入：samples/{domain}/{file|profile|task_template}
perspective/                  # 跨 domain 公共视角建模（agent/模型/迷你生成器）
llm_client/                   # DeepSeek 客户端 + 配置（.env）
supervisor/                   # 全局监督标准（prompt 注入，不单独调 LLM）
schema_repair/                # 结构化输出修复（LLM 输出非法时）
tools/
  runtime_context.py          # 领域加载 / 任务别名 / env 默认路径
  cli.py                      # CLI 参数解析与模板参数收集
  io.py                       # 输入文本和用户画像读取
  runner.py                   # 任务运行循环：流式输出 + done 事件处理
  archive.py                  # output/{domain}/{task}/ 归档
  exporters.py                # mindmap / knowledge_graph 产物导出编排
  contracts.py                # 契约 DSL（GenerationContract / SupervisorContract）
  fallback_rules.py           # 降级拼装规则 DSL（Raw / Join / Lines）
  validation.py               # 输出校验工具
  prompt_utils.py / template_prompt.py   # 渲染 prompt 构建
  template_router.py          # 模板路由：占位符/格式规范/自然语言三类自动判型 + 编译
  mindmap.py                  # 思维导图导出：markmap-cli（HTML）+ Playwright（PNG）
  knowledge_graph.py          # 知识图谱导出：nodes/edges → PNG/SVG/交互式 HTML
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

Linux 推荐配置：

| 目的 | Ubuntu / Debian | CentOS / RHEL / Fedora | 验证命令 |
|---|---|---|---|
| Python 运行环境 | `sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv` | `sudo dnf install -y python3 python3-pip` | `python3 --version` |
| 知识图谱 PNG/SVG | `sudo apt-get install -y graphviz fonts-noto-cjk` | `sudo dnf install -y graphviz google-noto-sans-cjk-fonts` | `dot -V` |
| 思维导图 HTML | `sudo apt-get install -y nodejs npm` | `sudo dnf install -y nodejs npm` | `node -v && npx -v` |
| 思维导图 PNG | `python3 -m playwright install --with-deps chromium` | `python3 -m playwright install chromium` | `python3 -m playwright --version` |

可选前置（按需）：

```bash
# 思维导图 HTML 导出需要 Node.js（npx 首次自动下载 markmap-cli，无需全局安装）
# 思维导图 PNG 导出还需要浏览器内核：
python -m playwright install chromium
```

> 知识图谱的 PNG/SVG 依赖系统 Graphviz，不是 Python 包；只 `pip install -r requirements.txt` 不会安装 `dot`。

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

#### Gradio 测试平台

```bash
python gradio_app.py
```

打开终端提示的本地地址后，可以在页面中选择领域、任务线和服务器样例文件。运行完成后，页面右侧会显示运行记录、PNG 预览，以及可下载后查看的产物文件（如 HTML / SVG / PNG / JSON / Markdown）。

平台标题：**XiaoYi-TaskAgent**

#### 服务器部署

Gradio 页面会从项目根目录的 `samples/` 中读取服务器侧文件，适合部署到 Linux 服务器后直接选择样例运行。

推荐目录约定：

| 目录 | 用途 | 页面中的控件 |
|---|---|---|
| `samples/{domain}/file/` | 输入文本 `.txt` | 服务器输入文本 |
| `samples/{domain}/profile/` | 用户画像 `.json` | 服务器用户画像 |
| `samples/{domain}/{task}_template/` | 任务模板 `.md` / `.txt` | 服务器模板文件 |
| `output/{domain}/{task}/` | 运行结果归档 | 页面预览 / 下载 |

服务器首次部署示例：

```bash
cd /path/to/AgentFlow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Ubuntu / Debian 如果需要思维导图 PNG 截图，建议安装 Playwright 系统依赖：

```bash
python -m playwright install --with-deps chromium
```

启动服务：

| 场景 | 命令 |
|---|---|
| 本机测试 | `python gradio_app.py` |
| 服务器外部访问 | `GRADIO_SERVER_NAME=0.0.0.0 GRADIO_SERVER_PORT=7860 python gradio_app.py` |
| 临时公网分享 | `GRADIO_SHARE=true python gradio_app.py` |
| 后台运行 | `nohup env GRADIO_SERVER_NAME=0.0.0.0 GRADIO_SERVER_PORT=7860 python gradio_app.py > gradio.log 2>&1 &` |

部署注意事项：

| 项目 | 说明 |
|---|---|
| API Key | 项目根目录需要 `.env`，至少配置 `DEEPSEEK_API_KEY` |
| 访问地址 | 云服务器需要开放安全组 / 防火墙端口，例如 `7860` |
| 文件选择 | 页面中的服务器文件来自 `项目绝对路径/samples/`，不是浏览器本地文件系统 |
| 输出保存 | 所有任务都会自动创建并写入 `output/{domain}/{task}/` |
| 知识图谱 | PNG/SVG 需要系统安装 Graphviz；HTML 可用于交互演示 |
| 思维导图 | HTML 需要 Node.js/npx；PNG 需要 Playwright Chromium |

#### 命令行

常用任务：

| 场景 | 命令 |
|---|---|
| 会议纪要 + 待办 | `python bootstrap.py --task minutes_generation --task action_items` |
| 思维导图演示 | `python bootstrap.py --task mindmap` |
| 笔记知识点 | `python bootstrap.py --domain notes --task points` |
| 知识图谱演示 | `python bootstrap.py --domain notes --task knowledge_graph` |

Linux/macOS 路径写法示例：

```bash
python3 bootstrap.py --domain notes --task knowledge_graph \
  --file student_math_notes.txt \
  --profile object_profile.json
```

Windows PowerShell 路径写法示例：

```bash
# 指定任务线（可多值）
python bootstrap.py --task minutes_generation --task action_items \
  --file meeting_all.txt \
  --profile object_profile.json

# 思维导图：默认同时输出 HTML 和 PNG 到 output/meeting/mindmap/
python bootstrap.py --task mindmap \
  --file meeting_all.txt \
  --profile object_profile.json

# 笔记域：知识点总结 + 知识图谱
python bootstrap.py --domain notes --task points --file student_math_notes.txt --profile object_profile.json

# 笔记域：知识图谱（默认输出 PNG/SVG/HTML 到 output/notes/knowledge_graph/；PNG/SVG 需系统安装 Graphviz）
python bootstrap.py --domain notes --task knowledge_graph --file student_math_notes.txt --profile object_profile.json
```

CLI 参数：

| 参数 | 是否必填 | 默认值 | 说明 | 示例 |
|---|---:|---|---|---|
| `--domain` | 否 | `meeting` | 选择领域。会议域用 `meeting`，笔记域用 `notes`。 | `--domain notes` |
| `--task` | 是 | 无 | 要运行的任务线，可重复传多个。 | `--task minutes_generation --task action_items` |
| `--file` | 否 | `samples/{domain}/file` | 输入 `.txt` 文件、目录，或 `samples/{domain}/file` 下的文件名。 | `--file student_math_notes.txt` |
| `--profile` | 否 | `samples/{domain}/profile` | 用户画像 `.json` 文件、目录，或 `samples/{domain}/profile` 下的文件名。 | `--profile object_profile.json` |
| `--env` | 否 | `./.env` | 环境变量文件路径。 | `--env ./.env` |
| `--{线名}_template` | 否 | 无 | 指定某条任务线的渲染模板。 | `--minutes_generation_template ./template.md` |

根目录 `samples/` 与终端参数一一对应：

| 目录 | 对应参数 | 当前样例 |
|---|---|---|
| `samples/meeting/file/` | `--domain meeting --file` | `meeting_all.txt` |
| `samples/meeting/profile/` | `--domain meeting --profile` | `object_profile.json` |
| `samples/meeting/minutes_generation_template/` | `--minutes_generation_template` | `simple_minutes.md` / `project_progress.md` / `test.md` |
| `samples/meeting/action_items_template/` | `--action_items_template` | `action_items.md` |
| `samples/meeting/risk_template/` | `--risk_template` | 可放置 `.md` 模板 |
| `samples/meeting/mindmap_template/` | `--mindmap_template` | 可放置 `.md` 模板 |
| `samples/notes/file/` | `--domain notes --file` | `student_math_notes.txt` |
| `samples/notes/profile/` | `--domain notes --profile` | `object_profile.json` |
| `samples/notes/points_template/` | `--points_template` | 可放置 `.md` 模板 |
| `samples/notes/knowledge_graph_template/` | `--knowledge_graph_template` | 可放置 `.md` 模板 |

路径解析规则：

| 写法 | 解析方式 |
|---|---|
| 不传 `--file` | 自动读取 `samples/{domain}/file/`，目录内必须只有一个 `.txt` |
| `--file student_math_notes.txt` | 自动解析为 `samples/{domain}/file/student_math_notes.txt` |
| `--file ./some/path/input.txt` | 使用项目根目录下的显式路径 |
| 不传 `--profile` | 自动读取 `samples/{domain}/profile/`，目录内必须只有一个 `.json` |
| `--profile object_profile.json` | 自动解析为 `samples/{domain}/profile/object_profile.json` |
| 不传 `--xx_template` | 自动查看 `samples/{domain}/xx_template/`；目录为空则不用模板，只有一个模板则自动使用 |
| `--xx_template simple.md` | 自动解析为 `samples/{domain}/xx_template/simple.md` |

模板参数是按当前 `--domain` 动态注册的。可用参数如下：

| 领域 | 任务线 | 模板参数 | 环境变量 | 说明 |
|---|---|---|---|---|
| `meeting` | `minutes_generation` | `--minutes_generation_template` | `MEETING_MINUTES_GENERATION_TEMPLATE` | 会议纪要输出模板 |
| `meeting` | `action_items` | `--action_items_template` | `MEETING_ACTION_ITEMS_TEMPLATE` | 待办事项输出模板 |
| `meeting` | `risk` | `--risk_template` | `MEETING_RISK_TEMPLATE` | 风险分析输出模板 |
| `meeting` | `mindmap` | `--mindmap_template` | `MEETING_MINDMAP_TEMPLATE` | 思维导图 Markdown 大纲模板 |
| `notes` | `points` | `--points_template` | `NOTES_POINTS_TEMPLATE` | 笔记知识点输出模板 |
| `notes` | `knowledge_graph` | `--knowledge_graph_template` | `NOTES_KNOWLEDGE_GRAPH_TEMPLATE` | 知识图谱 Markdown 大纲模板；不传模板时直接导出 PNG/SVG/HTML |

任务线：

| 领域 | 任务线 | 输出内容 | 主要产物 |
|---|---|---|---|
| `meeting` | `minutes_generation` | 会议纪要 | 终端文本 |
| `meeting` | `action_items` | 待办事项 | 终端文本 |
| `meeting` | `risk` | 风险分析 | 终端文本 |
| `meeting` | `mindmap` | 思维导图 | `output/meeting/mindmap/mindmap_*.png` / `.html` |
| `notes` | `points` | 笔记知识点总结 | 终端文本 |
| `notes` | `knowledge_graph` | 知识图谱 | `output/notes/knowledge_graph/knowledge_graph_*.png` / `.svg` / `.html` |

输出归档规则：

| 目录 | 内容 | 说明 |
|---|---|---|
| `output/{domain}/{task}/report_时间戳.json` | 完整最终数据 | 除 `knowledge_graph` 外的任务线都会保存，包含结构化字段和质量提示 |
| `output/{domain}/{task}/result_时间戳.md` | 最终文本 / 大纲 | 除 `knowledge_graph` 外，仅当该任务线有文本正文或 Markdown 大纲时保存 |
| `output/meeting/mindmap/mindmap_时间戳.html` | 思维导图 HTML | `mindmap` 线额外产物 |
| `output/meeting/mindmap/mindmap_时间戳.png` | 思维导图 PNG | `mindmap` 线额外产物；Playwright 不可用时跳过 |
| `output/notes/knowledge_graph/knowledge_graph_时间戳.png` | 知识图谱 PNG | `knowledge_graph` 线额外产物；Graphviz 不可用时跳过 |
| `output/notes/knowledge_graph/knowledge_graph_时间戳.svg` | 知识图谱 SVG | 高清矢量图，适合演示 |
| `output/notes/knowledge_graph/knowledge_graph_时间戳.html` | 知识图谱交互 HTML | Cytoscape.js 交互演示版；知识图谱目录只保留 PNG/SVG/HTML |

知识图谱输出文件：

| 文件 | 用途 | 依赖 | 说明 |
|---|---|---|---|
| `knowledge_graph_时间戳.png` | 快速预览、图片粘贴 | Graphviz `dot` | 位图，放大后可能变糊 |
| `knowledge_graph_时间戳.svg` | PPT/浏览器高清演示 | Graphviz `dot` | 矢量图，中文和线条缩放更清楚 |
| `knowledge_graph_时间戳.html` | 交互演示 | 浏览器；联网可加载 Cytoscape.js CDN | 可缩放、拖拽、点击节点/关系查看定义和 evidence |

可选环境变量（.env，均有默认值）：

```
MEETING_FILE=<会议文本路径>                     # 对应 --file
MEETING_PROFILE=<用户画像路径>                  # 对应 --profile
MEETING_MINUTES_GENERATION_TEMPLATE=<模板路径>  # 对应 --minutes_generation_template
NOTES_FILE=<笔记文本路径>                       # 对应 --file
NOTES_PROFILE=<用户画像路径>                    # 对应 --profile
NOTES_KNOWLEDGE_GRAPH_TEMPLATE=<模板路径>       # 对应 --knowledge_graph_template
```

## 自定义输出模板

用 `--{线名}_template` 指定对应任务线的渲染模板（`.md` 文件）。每个任务线一个参数：

| 任务线 | 模板参数 |
|---|---|
| minutes_generation | `--minutes_generation_template` |
| action_items | `--action_items_template` |
| risk | `--risk_template` |
| mindmap | `--mindmap_template` |
| points | `--points_template` |
| knowledge_graph | `--knowledge_graph_template` |

模板支持三种形式，系统**自动判型**处理：

| 形式 | 示例 | 处理方式 |
|---|---|---|
| **占位符模板** | `# [会议主题]` / `\| [任务] \| [负责人] \|` | 固定文字逐字符保留，LLM 只填占位符 |
| **格式规范模板** | 格式说明 + 输入/输出示例（如 JSON 数组） | 指令/示例分离，示例作 few-shot |
| **自然语言描述** | "第一行是标题，括号里跟时间和人物" | LLM 先编译成占位符模板再填充 |

```bash
python bootstrap.py --task minutes_generation --file ... --profile ... \
  --minutes_generation_template simple_minutes.md

python bootstrap.py --domain notes --task knowledge_graph \
  --file student_math_notes.txt \
  --profile object_profile.json \
  --knowledge_graph_template <模板文件名>.md
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
⑦ python bootstrap.py --task xxx --file ... --profile ...
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
- **思维导图**：mindmap 线产出 Markdown 大纲，经 `tools/mindmap.py` 固定导出
  交互式 HTML（markmap，离线单文件）和 PNG 图片（Playwright 截图）；
  npx/playwright 缺失时自动降级不影响主流程
- **知识图谱**：notes 域 knowledge_graph 线提取概念节点与关系边（nodes/edges，
  均锚定原文 + evidence），经 `tools/knowledge_graph.py` 同时导出 PNG、SVG
  和 Cytoscape.js 交互式 HTML（默认输出到 `output/notes/knowledge_graph/`）；悬空边自动过滤、
  中文 label 自动探测字体，dot 缺失时 PNG/SVG 自动跳过，HTML 仍尽量生成
- **输出稳定性**：各线 prompt 采用确定性规则（数量由内容决定、措辞锚定原文、
  顺序按原文出现、空字段 null/[]），同一输入重复运行保持内容与篇幅稳定
