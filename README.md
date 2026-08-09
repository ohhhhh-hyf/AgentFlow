# 个性化会议纪要多 Agent 系统

基于 DeepSeek 的会议纪要/待办生成系统：双任务线并行流水线（纪要 + 待办），
每条线独立执行"生成 → 领域审核（+全局标准注入）→ 渲染"，互不阻塞；
支持客观视角与个人视角；可扩展任意新任务线。

## 项目结构

```
bootstrap.py                  # CLI 入口
domain/
  meeting/
    domain_config.py          # 领域配置：STATE_CLASS / LINE_CN_NAMES（中文名注册表）
    models.py                 # 数据模型 + 各线生成模型/审核模型（生成区）
    reports.py                # 全部任务线最终输出 Report 类（手写区）
    orchestrator.py           # 双线并行图 + 节点 + run/run_streaming
    meeting_factory.py        # Agent 依赖组装工厂
    meeting_core/             # 核心层：会议理解 + 视角建模
    tasks/
      minutes_generation/     # 纪要线（contracts.py / prompts.py / steps/）
      action_items/           # 待办线（contracts.py / prompts.py / steps/）
      ...                     # 新增任务线同构
      {line}/steps/           # agent / supervisor / render 三步骤实现
    samples/                  # 示例会议文本 / 用户画像 / 模板
llm_client/                   # DeepSeek 客户端 + 配置（.env）
supervisor/                   # 全局监督标准（prompt 注入，不单独调 LLM）
schema_repair/                # 结构化输出修复（LLM 输出非法时）
tools/
  contracts.py                # 契约 DSL（GenerationContract / SupervisorContract）
  fallback_rules.py           # 降级拼装规则 DSL（Raw / Join / Lines）
  validation.py               # 输出校验工具
  prompt_utils.py / template_prompt.py   # 渲染 prompt 构建
  scripts/
    codegen.py                # 代码生成器：从契约生成模型/装配/骨架（--write/--check）
    register.py               # 新增任务线第一步：注册 + 骨架 + 工厂 import
```

## 快速开始

### 1. 环境准备

```bash
# Python >= 3.10，安装依赖
pip install -r requirements.txt
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
# 全部任务线（纪要 + 待办）
python bootstrap.py --summary .\domain\meeting\samples\summary\meeting_all.txt --profile .\domain\meeting\samples\profile\object_profile.json

# 指定任务线（可多值）
python bootstrap.py --task minutes_generation --task action_items --summary ... --profile ...

# 自定义渲染模板
python bootstrap.py ... --minutes_template .\domain\meeting\samples\summary_template\simple_minutes.md
```

## 新增任务线（如"风险管理"）

手写 4 处 + 命令 4 条（以线名 `xxx`、中文名 `xxx` 为例）：

```
① 手写 domain/meeting/tasks/xxx/contracts.py      # 生成/审核契约 + 降级规则
② python tools/scripts/register.py --domain meeting --task xxx --name "中文名"
   # 自动：注册中文名 + steps/ 三件套 + 工厂 import + 占位校验类
③ 手写 domain/meeting/tasks/xxx/prompts.py         # 4 个 prompt 常量
④ reports.py 末尾追加 XxxReport 类（继承 ModelMixin, XxxReportValidation）
⑤ python tools/scripts/codegen.py --domain meeting   # 全量生成 → SUCCESS!
⑥ python tools/scripts/codegen.py --domain meeting --check   # 校验 → SUCCESS!
⑦ python bootstrap.py --task xxx --summary ... --profile ...
```

## 架构要点

- **双线并行**：纪要/待办各自监督返工闭环（approve/revise≤1次/reject→降级），互不阻塞
- **契约驱动**：每条任务线的模型/校验/装配由 `contracts.py` 声明，`codegen.py` 生成
- **生成区**：`models.py` / `orchestrator.py` / `meeting_factory.py` 的生成区由脚本管理
  （`--write` 重写、`--check` 校验），手写区（contracts/prompts/reports 类）脚本不碰
- **全局标准注入**：`supervisor/` 的全局标准经 `GlobalSupervisor.build_prompt` 注入各线 supervisor
- **占位校验**：register 阶段预生成 `XxxReportValidation: pass`，写 Report 类无 NameError，
  codegen 全量后按字段生成真实校验
