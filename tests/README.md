# 测试目录说明

## 目录结构

```
tests/
├── conftest.py          # 全局路径、环境隔离、基础 fixture
├── support/             # 非测试辅助代码（pytest 不收集）
│   ├── builders.py      # Minutes 草稿 / MeetingFact / 共享上下文构造器
│   ├── fakes.py         # MagicMock 客户端与 minutes 图驱动
│   └── expectations.py  # expect()：失败即 AssertionError
├── unit/                # 单包测试，镜像 app/ core/ domains/ infra/
├── integration/         # 跨包 / 跨运行时边界
└── e2e/                 # 完整流程
```

`tests/unit/` 的路径镜像生产代码：

| 生产代码 | 单元测试 |
|---|---|
| `core/templates/router.py` | `tests/unit/core/templates/test_router.py` |
| `domains/meeting/tasks/minutes/prompts.py` | `tests/unit/domains/meeting/tasks/minutes/test_prompts.py` |
| `infra/llm/client.py` | `tests/unit/infra/llm/test_client.py` |

## 分层规则

- **unit**：只导入 1 个顶级包（`app` / `core` / `domains` / `infra`），不启动真实 runner、不访问网络、不写仓库目录。
- **integration**：导入 ≥2 个顶级包，或需要真实 runner / 模板资源 / 跨模块协作。
- **e2e**：从输入到图执行再到产物导出的完整链路。
- 标记：`tests/integration/**` 文件统一带 `pytestmark = pytest.mark.integration`；`tests/e2e/**` 带 `pytestmark = pytest.mark.e2e`；unit 不加 marker，靠路径筛选。

## 命名与写法

- 文件：`test_<subject>_<behavior>.py`，单个文件 ≤ 500 行。
- 函数：`test_<behavior>_<expected>()`，一个函数只验证一个行为。
- 断言：优先 `assert`；需要附加诊断信息时用 `from tests.support.expectations import expect`。
- 异常：用 `pytest.raises(...)`。
- 禁止只调用 `check()` / 只 print 的静默测试。

## 运行

```bash
# 全量
python -m pytest tests -q

# 只跑单元
python -m pytest tests/unit -q

# 只跑集成 / 端到端
python -m pytest -m integration -q
python -m pytest -m e2e -q

# 跳过需要真实模型/网络的用例
python -m pytest tests -m "not llm" -q

# 覆盖率（门槛 47%）
python -m pytest tests -m "not llm" -q \
  --cov=app --cov=core --cov=domains --cov=infra \
  --cov-report=term-missing --cov-fail-under=47
```

`python -m tests` 也会跑全量（见 `tests/__main__.py`）。

## 新增测试

1. 找到被测生产模块。
2. 只导入一个顶级包 → 放 `tests/unit/<镜像路径>/`；跨包 → `tests/integration/<领域>/`；完整流程 → `tests/e2e/`。
3. 文件名镜像模块名，例如 `domains/meeting/tasks/minutes/prompts.py` → `tests/unit/domains/meeting/tasks/minutes/test_prompts.py`。
4. 数据准备用 `tmp_path` / `monkeypatch`；共享构造逻辑放 `tests/support/`。
5. 单元测试不要读写仓库 `data/`、`logs/`；需要文件时用 `tmp_path`。
6. 新测试必须能在失败时真正变红（assert / expect / pytest.raises）。

## 隔离与 CI

- `tests/conftest.py` 启动时把 `AGENTFLOW_DATA_DIR` / `AGENTFLOW_LOG_DIR` / 日志文件指向会话级临时目录，退出自动清理。
- 无 `.env` 时自动设置占位 `DEEPSEEK_API_KEY` / `SILICONFLOW_API_KEY`，CI 不依赖本地密钥。
- 开发依赖：`pip install -r requirements-dev.txt`。
- CI：`.github/workflows/tests.yml`，push/PR 跑 `-m "not llm"` 并校验覆盖率；每周一跑 `-m llm`。
