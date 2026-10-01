# Tools —— 离线研发与运维工具集

本目录汇集离线研发脚手架工具与本地运维调试脚本，**不属于生产线上运行链路**。

---

## 架构单向依赖红线 (One-Way Dependency Rule)

> [!CAUTION]
> **绝对禁止生产运行时代码反向导入 `tools/`**！
> 
> - `app/`、`core/`、`domains/`、`infra/` 属于生产运行时代码，绝对不能包含任何 `from tools...` 或 `import tools...` 语句。
> - `tools/` 仅由研发人员在本地终端（CLI）或 CI 流程中离线运行，用于生成骨架、校验一致性及本地数据排查。

---

## 目录结构

```text
tools/
├── README.md               # 本规范说明文件
├── codegen/                # 领域与任务线代码生成脚手架
│   ├── README.md           # 代码生成规则与详细文档
│   ├── register_domain.py  # 新建领域骨架（目录 + 模板渲染 + 生成区初始化）
│   ├── register_task.py    # 新建任务线骨架（契约 + 提示词 + 步骤 + 报表追加）
│   ├── sync_domain.py      # 一键同步/校验全量生成区（AST 解析驱动）
│   └── domain_template/    # 领域模板文件池（.py.tpl）
└── devtools/               # 本地运维与数据排查脚本
    ├── check_user_profile.py # 秒级离线自检用户画像解析与注入
    └── purge_kb_source.py    # 按来源清理知识库旧知识块
```

---

## 常用 CLI 命令

### 1. 领域与任务线脚手架 (`tools/codegen/`)

详见 [tools/codegen/README.md](file:///D:/study/demo/tools/codegen/README.md)。

- **新建领域**：
  ```bash
  python tools/codegen/register_domain.py --domain notes --name "笔记"
  ```
- **新建任务线**：
  ```bash
  python tools/codegen/register_task.py --domain notes --task digest --name "摘要" --with-report
  ```
- **生成并校验代码生成区**：
  ```bash
  # 仅生成模型与报表校验
  python tools/codegen/sync_domain.py --domain notes --model

  # 写入全量生成区
  python tools/codegen/sync_domain.py --domain notes

  # CI 一致性校验（检查代码生成区是否与契约完全对齐）
  python tools/codegen/sync_domain.py --domain meeting --check
  python tools/codegen/sync_domain.py --domain notes --check
  ```

### 2. 运维与排查工具 (`tools/devtools/`)

- **自检用户画像与偏好注入（不调 LLM，秒级）**：
  ```bash
  python tools/devtools/check_user_profile.py 1 --show-block
  ```
- **知识库来源清理**：
  ```bash
  # 查看某用户学科下的知识库文件来源
  python tools/devtools/purge_kb_source.py --user 1 --subject 物理 --list

  # 清理旧的 OCR 知识块
  python tools/devtools/purge_kb_source.py --user 1 --subject 物理 --source "ocr_*"
  ```
