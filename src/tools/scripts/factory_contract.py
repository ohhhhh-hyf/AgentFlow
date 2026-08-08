"""factory_contract.py —— 从 tasks/ 目录生成 MeetingAgentFactory.create() 的任务线装配代码。

读取 ``src/domain/meeting/tasks/`` 下每个任务线目录，按统一命名约定
（类名 = PascalCase(线名) + Agent/Supervisor/Render）生成 create() 函数体
内的三行实例化代码，写入 meeting_factory.py 的装配生成区。

命名约定（强制，与现有代码一致）：
- 任务线 = ``tasks/{线名}/`` 子目录（如 tasks/minutes_generation/）
- 类名 = ``PascalCase(线名)`` + ``Agent`` / ``Supervisor`` / ``Render``
- 文件 = ``{线名}_agent.py`` / ``{线名}_supervisor.py`` / ``{线名}_render.py``

用法：
    python tools/scripts/factory_contract.py             # 生成并打印
    python tools/scripts/factory_contract.py --write     # 写入 meeting_factory.py 生成区
    python tools/scripts/factory_contract.py --check     # 校验生成区与目录一致（CI 用）

生成区标记（meeting_factory.py 的 create() 函数体内）：
    # ── 任务线装配生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──
    ...（每条线 3 行：agent / supervisor / render）...
    # ── 任务线装配生成区结束 ──
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# 项目根（脚本位于 src/tools/scripts/factory_contract.py）
ROOT = Path(__file__).resolve().parents[3]
TASKS_DIR = ROOT / "src" / "domain" / "meeting" / "tasks"
FACTORY_PATH = ROOT / "src" / "domain" / "meeting" / "meeting_factory.py"
ORCH_PATH = ROOT / "src" / "domain" / "meeting" / "orchestrator.py"
MODELS_PATH = ROOT / "src" / "domain" / "meeting" / "models.py"

# 脚本需读 LINE_CN_NAMES（渲染上下文生成用中文名）
sys.path.insert(0, str(ROOT / "src"))
from domain.meeting.line_registry import LINE_CN_NAMES  # noqa: E402

# 任务线装配生成区标记（meeting_factory.py 的 create() 函数体内）
ZONE_START = "# ── 任务线装配生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
ZONE_END = "# ── 任务线装配生成区结束 ──"

# 专属节点方法生成区标记（orchestrator.py 的 _Nodes 类内）
# 语义与纯生成区不同：脚本只生成骨架（签名 + 占位注释），函数体由开发者填写；
# --write 遇已有实现跳过，--check 只验证签名存在，不比较函数体。
NODE_ZONE_START = "# ── 专属节点方法生成区：由 tools/scripts/factory_contract.py 生成骨架，函数体可改 ──"
NODE_ZONE_END = "# ── 专属节点方法生成区结束 ──"

# 任务线注册生成区标记（orchestrator.py 模块级 TASK_LINES 定义）
TL_ZONE_START = "# ── 任务线注册生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
TL_ZONE_END = "# ── 任务线注册生成区结束 ──"

# Agent 挂载生成区标记（orchestrator.py 的 __init__ 内，任务线挂载）
MOUNT_ZONE_START = "# ── Agent 挂载生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
MOUNT_ZONE_END = "# ── Agent 挂载生成区结束 ──"

# 节点映射生成区标记（orchestrator.py 的 __init__ 内，_fallback_nodes）
NODEMAP_ZONE_START = "# ── 节点映射生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
NODEMAP_ZONE_END = "# ── 节点映射生成区结束 ──"

# 渲染上下文生成区标记（orchestrator.py 的 _Nodes 类内，完整生成勿手改）
CTX_ZONE_START = "# ── 渲染上下文生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
CTX_ZONE_END = "# ── 渲染上下文生成区结束 ──"

# FallbackRules import 生成区标记（orchestrator.py 顶部 import 区，整体生成勿手改）
IMPORT_ZONE_START = "# ── FallbackRules import 生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
IMPORT_ZONE_END = "# ── FallbackRules import 生成区结束 ──"

# Report import 生成区标记（orchestrator.py 顶部 import 区，整体生成勿手改）
REPORT_IMPORT_ZONE_START = "# ── Report import 生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
REPORT_IMPORT_ZONE_END = "# ── Report import 生成区结束 ──"

# Report 组装器生成区标记（orchestrator.py 的 __init__ 内，整体生成勿手改）
REPORT_ZONE_START = "# ── Report 组装器生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
REPORT_ZONE_END = "# ── Report 组装器生成区结束 ──"

# FallbackRules 注册生成区标记（orchestrator.py 的 __init__ 内，整体生成勿手改）
FALLBACK_RULES_ZONE_START = "# ── FallbackRules 注册生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
FALLBACK_RULES_ZONE_END = "# ── FallbackRules 注册生成区结束 ──"

# 生成区正则：允许标记前有缩进（生成区嵌在 create() 函数体内，行首带空格）
_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(ZONE_END)
)

# 节点方法生成区正则（同样允许缩进，生成区在类内）
_NODE_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(NODE_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(NODE_ZONE_END)
)

# 任务线注册生成区正则（模块级顶格）
_TL_ZONE_PATTERN = (
    re.escape(TL_ZONE_START)
    + r"\r*\n(.*?)\r*\n"
    + re.escape(TL_ZONE_END)
)

# Agent 挂载生成区正则（__init__ 方法体内，行首 8 空格缩进）
_MOUNT_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(MOUNT_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(MOUNT_ZONE_END)
)

# 节点映射生成区正则（__init__ 方法体内，行首 8 空格缩进）
_NODEMAP_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(NODEMAP_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(NODEMAP_ZONE_END)
)

# 渲染上下文生成区正则（_Nodes 类内，行首 4 空格缩进）
_CTX_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(CTX_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(CTX_ZONE_END)
)

# FallbackRules import 生成区正则（模块级顶格）
_IMPORT_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(IMPORT_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(IMPORT_ZONE_END)
)

# Report import 生成区正则（模块级顶格）
_REPORT_IMPORT_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(REPORT_IMPORT_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(REPORT_IMPORT_ZONE_END)
)

# Report 组装器生成区正则（__init__ 方法体内，行首 8 空格缩进）
_REPORT_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(REPORT_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(REPORT_ZONE_END)
)

# FallbackRules 注册生成区正则（__init__ 方法体内，行首 8 空格缩进）
_FALLBACK_RULES_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(FALLBACK_RULES_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(FALLBACK_RULES_ZONE_END)
)


# ── 发现与命名 ──────────────────────────────────────────────

def find_lines(tasks_dir: Path | None = None) -> list[str]:
    """扫描 tasks/ 目录，返回全部任务线名（按名称排序）。"""
    tasks_dir = tasks_dir or TASKS_DIR
    return sorted(
        d.name
        for d in tasks_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )


def line_class_name(line: str, suffix: str) -> str:
    """线名 + 后缀 → 类名。例：risk + Agent → RiskAgent。"""
    prefix = "".join(part.capitalize() for part in line.split("_"))
    return f"{prefix}{suffix}"


# ── 代码生成 ─────────────────────────────────────────────────

def generate_lines_code(lines: list[str]) -> str:
    """生成装配代码：每条线 3 行（agent / supervisor / render）。

    键名统一为 ``{line}_agent`` / ``{line}_supervisor`` / ``{line}_render``，
    与 __init__ 挂载的属性名、TASK_LINES 的 agent_attr 完全一致
    （一个名字贯穿工厂→挂载→注册表→getattr）。

    行首不带缩进（写入时由 _write_target 统一加 create() 函数体缩进）。
    """
    blocks = []
    for line in lines:
        blocks.append(
            f'"{line}_agent": {line_class_name(line, "Agent")}(client),'
            f'\n"{line}_supervisor": {line_class_name(line, "Supervisor")}(client),'
            f'\n"{line}_render": {line_class_name(line, "Render")}(client),'
        )
    return "\n".join(blocks)


def _has_fallback_rules(line: str, tasks_dir: Path | None = None) -> bool:
    """该线 contracts.py 是否声明 FallbackRules 子类（有则生成完整 fallback 节点）。"""
    tasks_dir = tasks_dir or TASKS_DIR
    contracts_path = tasks_dir / line / "contracts.py"
    if not contracts_path.exists():
        return False
    return bool(
        re.search(
            r"class\s+\w+FallbackRules\b",
            contracts_path.read_text(encoding="utf-8"),
        )
    )


def generate_node_skeleton(line: str, tasks_dir: Path | None = None) -> str:
    """生成单线降级节点。

    - 该线 contracts.py 声明了 ``FALLBACK_RULES`` → 生成**完整函数体**
      （调用公共拼装器 ``_fallback_text``，引用 ``{BASE}_FALLBACK_RULES``）
    - 未声明 → 生成默认骨架（占位 return，开发者手写实现）
    """
    fn = f"_{line}_fallback_node"
    if _has_fallback_rules(line, tasks_dir):
        base = _contract_base(line, tasks_dir)
        return (
            f"    async def {fn}(self, state: MeetingState) -> dict:\n"
            f"        text, items = _fallback_text(\n"
            f'            state, "{line}", {base}_FALLBACK_RULES)\n'
            f'        line_dict = {{"rendered": text, "degraded": True}}\n'
            f"        if items is not None:\n"
            f'            line_dict["items"] = items\n'
            f'        return {{\"lines\": {{\"{line}\": line_dict}}, '
            f'"quality_degraded": True}}\n'
        )
    return (
        f"    async def {fn}(self, state: MeetingState) -> dict:\n"
        f"        ## 这里新增你的代码：降级输出（写入 "
        f'lines["{line}"]["rendered"] + degraded）\n'
        f"        ## 未实现时返回空降级兜底（保证可运行）；实现后请替换下方 return\n"
        f'        return {{"lines": {{"{line}": {{"rendered": "（降级）", '
        f'"degraded": True}}}}, "quality_degraded": True}}\n'
    )


def generate_node_skeletons(lines: list[str]) -> str:
    """生成全部线的专属节点方法骨架（仅 fallback，按线排序）。"""
    blocks = []
    for line in lines:
        blocks.append(generate_node_skeleton(line))
    return "\n".join(blocks)


# ── TASK_LINES 注册生成 ──────────────────────────────────────

def _contract_base(line: str, tasks_dir: Path | None = None) -> str:
    """线名 → 契约基名：从该线 contracts.py 的契约类名推导。

    例：minutes_generation/contracts.py 里 MinutesGenerationContract
    → 类名去 GenerationContract 后缀 "Minutes" → 全大写 "MINUTES"
    （用于推导 _EMPTY_MINUTES / _REJECT_MINUTES_REVIEW）。
    """
    tasks_dir = tasks_dir or TASKS_DIR
    contracts_path = tasks_dir / line / "contracts.py"
    if not contracts_path.exists():
        raise ValueError(f"{contracts_path} 不存在（无法解析生成契约）")
    text = contracts_path.read_text(encoding="utf-8")
    for cls_name in re.findall(r"class\s+(\w+GenerationContract)\b", text):
        base = cls_name.removesuffix("GenerationContract")
        return re.sub(r"(?<!^)(?=[A-Z])", "_", base).upper()
    raise ValueError(
        f"{contracts_path} 未找到 *GenerationContract 生成契约类"
    )


def generate_task_lines_code(
    lines: list[str], tasks_dir: Path | None = None
) -> str:
    """生成 TASK_LINES 注册代码（模块级顶格，含类型注解与定义行）。"""
    blocks = []
    for line in lines:
        base = _contract_base(line, tasks_dir)
        blocks.append(
            f'    "{line}": {{\n'
            f'        "agent_attr": "{line}_agent",\n'
            f'        "supervisor_attr": "{line}_supervisor",\n'
            f'        "empty_draft": _EMPTY_{base},\n'
            f'        "reject_review": _REJECT_{base}_REVIEW,\n'
            f"    }},"
        )
    return "TASK_LINES: dict[str, dict] = {\n" + "\n".join(blocks) + "\n}"


# ── __init__ 挂载与节点映射生成 ──────────────────────────────

def generate_mount_code(lines: list[str]) -> str:
    """生成 __init__ 的 Agent 挂载代码（每条线 3 行，行首 8 空格缩进）。

    键名/属性名/类型注解全部由命名约定推导，与工厂键、TASK_LINES 对齐：
    ``self.{line}_{role}: {PascalCase(line)}{Role} = agents["{line}_{role}"]``
    """
    blocks = []
    for line in lines:
        for role, suffix in (
            ("agent", "Agent"),
            ("supervisor", "Supervisor"),
            ("render", "Render"),
        ):
            blocks.append(
                f"        self.{line}_{role}: {line_class_name(line, suffix)} = "
                f'agents["{line}_{role}"]'
            )
    return "\n".join(blocks)


def generate_node_map_code(lines: list[str]) -> str:
    """生成 __init__ 的降级节点映射（{} + 追加式，行首 8 空格缩进）。

    渲染节点已移除：``_render_nodes`` 不再存在，仅保留 ``_fallback_nodes``。
    """
    blocks = ["        self._fallback_nodes: dict[str, object] = {}"]
    blocks += [
        f'        self._fallback_nodes["{line}"] = self._{line}_fallback_node'
        for line in lines
    ]
    return "\n".join(blocks)


def generate_render_context_code(lines: list[str]) -> str:
    """生成 _Nodes 类的渲染上下文方法（完整生成，勿手改，行首 4 空格缩进）。

    所有线的 render_context 完全同构：视角模式 / 原文 / 画像 / 会议理解 /
    用户视角 / 已批准{中文名}草稿 / {中文名}审核结论。中文名查 LINE_CN_NAMES。
    """
    blocks = []
    for line in lines:
        cn = LINE_CN_NAMES.get(line, line)
        blocks.append(
            f"    def _{line}_render_context(self, state: MeetingState) -> str:\n"
            f"        mode = self._mode_label(state)\n"
            f'        line = _line(state, "{line}")\n'
            f'        review = line.get("supervisor_review") or {{}}\n'
            f"        return (\n"
            f'            f"视角模式：{{mode}}\\n"\n'
            f'            f"objective_perspective：'
            f"{{bool(state.get('objective_perspective'))}}\\n\\n\"\n"
            f'            f"会议原文：\\n{{state[\'transcript\']}}\\n\\n\"\n'
            f'            f"用户画像：\\n{{_json(state[\'user\'])}}\\n\\n\"\n'
            f'            f"已审核会议理解：\\n{{_json(state.get(\'meeting_understanding\'))}}\\n\\n\"\n'
            f'            f"已审核用户视角：\\n{{_json(state.get(\'perspective_profile\'))}}\\n\\n\"\n'
            f'            f"已批准{cn}草稿：\\n{{_json(line.get(\'draft\'))}}\\n\\n\"\n'
            f'            f"{cn}审核结论：\\n{{_json(review)}}"\n'
            f"        )\n"
        )
    return "\n".join(blocks)


def write_render_context(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的渲染上下文生成区。"""
    raw = _read_raw(path)
    if CTX_ZONE_START not in raw or CTX_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到渲染上下文生成区标记。请先手动添加：\n"
            f"    {CTX_ZONE_START}\n（现有手写 render_context 移入此处）\n"
            f"    {CTX_ZONE_END}"
        )
    m = re.search(_CTX_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中渲染上下文生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_render_context_code(lines).split("\n"))
    block = (
        f"    {CTX_ZONE_START}"
        + nl
        + nl
        + code
        + nl
        + nl
        + f"    {CTX_ZONE_END}"
    )
    new_raw = re.sub(
        _CTX_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path.name} 渲染上下文生成区")


def check_render_context(path: Path, lines: list[str]) -> int:
    """校验渲染上下文生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_CTX_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到渲染上下文生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_render_context_code(lines)
    if zone.strip() != expected.strip():
        print(
            f"不一致：渲染上下文生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    print(f"OK：渲染上下文生成区一致（{len(lines)} 条线）")
    return 0


def generate_fallback_import_code(lines: list[str]) -> str:
    """生成 orchestrator 顶部 FallbackRules import（模块级顶格）。

    每条线一行：``from .tasks.{线名}.contracts import {BASE}_FALLBACK_RULES``
    （BASE = 契约基名，如 MINUTES / ACTION_ITEMS）。
    """
    return "\n".join(
        f"from .tasks.{line}.contracts import "
        f"{_contract_base(line)}_FALLBACK_RULES"
        for line in lines
    )


def write_fallback_imports(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的 FallbackRules import 生成区。"""
    raw = _read_raw(path)
    if IMPORT_ZONE_START not in raw or IMPORT_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到 FallbackRules import 生成区标记。请先手动添加：\n"
            f"{IMPORT_ZONE_START}\n（现有手写 FallbackRules import 移入此处）\n"
            f"{IMPORT_ZONE_END}"
        )
    m = re.search(_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 FallbackRules import 生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_fallback_import_code(lines).split("\n"))
    block = (
        f"{IMPORT_ZONE_START}"
        + nl
        + nl
        + code
        + nl
        + nl
        + f"{IMPORT_ZONE_END}"
    )
    new_raw = re.sub(
        _IMPORT_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path.name} FallbackRules import 生成区")


def check_fallback_imports(path: Path, lines: list[str]) -> int:
    """校验 FallbackRules import 生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到 FallbackRules import 生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_fallback_import_code(lines)
    if zone.strip() != expected.strip():
        print(
            f"不一致：FallbackRules import 生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    print(f"OK：FallbackRules import 生成区一致（{len(lines)} 条线）")
    return 0


def _pascal(base: str) -> str:
    """契约基名 → PascalCase（"ACTION_ITEMS" → "ActionItems"）。"""
    return "".join(word.capitalize() for word in base.lower().split("_"))


def _report_class(line: str) -> str:
    """线名 → Report 类名：{PascalCase(契约基名)}Report。

    例：minutes_generation → MINUTES → MinutesReport；
        action_items → ACTION_ITEMS → ActionItemsReport。
    """
    return f"{_pascal(_contract_base(line))}Report"


def _has_report_class(line: str) -> bool:
    """models.py 是否已定义该线的 Report 类（未定义则不生成引用，避免 NameError）。"""
    return bool(
        re.search(
            rf"class\s+{re.escape(_report_class(line))}\b",
            MODELS_PATH.read_text(encoding="utf-8"),
        )
    )


def generate_report_import_code(lines: list[str]) -> str:
    """生成 orchestrator 顶部 Report import（模块级顶格，按线排序）。

    只包含 models.py 已定义的 Report 类；未定义（开发者还没写）的线跳过。
    """
    names = [cls for line in lines
             if _has_report_class(line) for cls in [_report_class(line)]]
    if not names:
        return ""
    return f"from .models import (\n    " + ",\n    ".join(names) + ",\n)"


def generate_report_assembler_code(lines: list[str]) -> str:
    """生成 __init__ 的 Report 组装器（行首 8 空格缩进）。

    ``self._report_assemblers = {线名: Report类}``——键 = 线名（与 chunk.line 一致），
    值 = models.py 手写区定义的 Report 类。
    """
    blocks = ["        self._report_assemblers = {"]
    for line in lines:
        if _has_report_class(line):
            blocks.append(f'            "{line}": {_report_class(line)},')
    blocks.append("        }")
    return "\n".join(blocks)


def write_report_imports(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的 Report import 生成区。"""
    raw = _read_raw(path)
    if REPORT_IMPORT_ZONE_START not in raw or REPORT_IMPORT_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到 Report import 生成区标记。请先手动添加：\n"
            f"{REPORT_IMPORT_ZONE_START}\n（现有手写 Report import 移入此处）\n"
            f"{REPORT_IMPORT_ZONE_END}"
        )
    m = re.search(_REPORT_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 Report import 生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = generate_report_import_code(lines)
    block = (
        f"{REPORT_IMPORT_ZONE_START}"
        + nl
        + (nl + code + nl if code else nl)
        + f"{REPORT_IMPORT_ZONE_END}"
    )
    new_raw = re.sub(
        _REPORT_IMPORT_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path.name} Report import 生成区")


def check_report_imports(path: Path, lines: list[str]) -> int:
    """校验 Report import 生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_REPORT_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到 Report import 生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_report_import_code(lines)
    if zone.strip() != expected.strip():
        print(
            f"不一致：Report import 生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    print(f"OK：Report import 生成区一致（{len(lines)} 条线）")
    return 0


def write_report_assemblers(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的 Report 组装器生成区。"""
    raw = _read_raw(path)
    if REPORT_ZONE_START not in raw or REPORT_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到 Report 组装器生成区标记。请先手动添加：\n"
            f"        {REPORT_ZONE_START}\n（现有手写 _report_assemblers 移入此处）\n"
            f"        {REPORT_ZONE_END}"
        )
    m = re.search(_REPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 Report 组装器生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_report_assembler_code(lines).split("\n"))
    block = (
        f"        {REPORT_ZONE_START}"
        + nl
        + nl
        + code
        + nl
        + nl
        + f"        {REPORT_ZONE_END}"
    )
    new_raw = re.sub(
        _REPORT_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path.name} Report 组装器生成区")


def check_report_assemblers(path: Path, lines: list[str]) -> int:
    """校验 Report 组装器生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_REPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到 Report 组装器生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_report_assembler_code(lines)
    if zone.strip() != expected.strip():
        print(
            f"不一致：Report 组装器生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    print(f"OK：Report 组装器生成区一致（{len(lines)} 条线）")
    return 0


def generate_fallback_rules_code(lines: list[str]) -> str:
    """生成 __init__ 的 FallbackRules 注册（行首 8 空格缩进）。

    ``self._fallback_rules = {线名: {BASE}_FALLBACK_RULES}``——图异常兜底
    （_fallback_reports）按线名取该线降级规则。只含声明了 FallbackRules 子类的线。
    """
    blocks = ["        self._fallback_rules = {"]
    for line in lines:
        if _has_fallback_rules(line):
            blocks.append(
                f'            "{line}": {_contract_base(line)}_FALLBACK_RULES,'
            )
    blocks.append("        }")
    return "\n".join(blocks)


def write_fallback_rules(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的 FallbackRules 注册生成区。"""
    raw = _read_raw(path)
    if FALLBACK_RULES_ZONE_START not in raw or FALLBACK_RULES_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到 FallbackRules 注册生成区标记。请先手动添加：\n"
            f"        {FALLBACK_RULES_ZONE_START}\n"
            f"（现有手写 _fallback_rules 移入此处）\n"
            f"        {FALLBACK_RULES_ZONE_END}"
        )
    m = re.search(_FALLBACK_RULES_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 FallbackRules 注册生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_fallback_rules_code(lines).split("\n"))
    block = (
        f"        {FALLBACK_RULES_ZONE_START}"
        + nl
        + nl
        + code
        + nl
        + nl
        + f"        {FALLBACK_RULES_ZONE_END}"
    )
    new_raw = re.sub(
        _FALLBACK_RULES_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path.name} FallbackRules 注册生成区")


def check_fallback_rules(path: Path, lines: list[str]) -> int:
    """校验 FallbackRules 注册生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_FALLBACK_RULES_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到 FallbackRules 注册生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_fallback_rules_code(lines)
    if zone.strip() != expected.strip():
        print(
            f"不一致：FallbackRules 注册生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    print(f"OK：FallbackRules 注册生成区一致（{len(lines)} 条线）")
    return 0


# ── 写入 / 校验（复用 generation_contract.py 的生成区模式）──

def _read_raw(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_target(path: Path, code: str) -> None:
    """把生成的装配代码写入指定文件的生成区（无标记则报错提示）。"""
    raw = _read_raw(path)
    if ZONE_START not in raw or ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到任务线装配生成区标记。请先手动添加：\n"
            f"{ZONE_START}\n（现有任务线装配代码移入此处）\n{ZONE_END}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    # 生成区内容缩进与 create() 函数体一致（12 空格），行尾与文件一致
    indented = nl.join(
        f"            {ln}" for ln in code.split("\n")
    )
    block = (
        f"            {ZONE_START}"
        + nl
        + nl
        + indented
        + nl
        + nl
        + f"            {ZONE_END}"
    )
    new_raw = re.sub(
        _ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path}")


def _normalize_newlines(text: str) -> str:
    return re.sub(r"\r*\n", "\n", text)


def _check_target(path: Path, code: str) -> int:
    """校验生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到任务线装配生成区标记", file=sys.stderr)
        return 1
    zone_lines = [
        ln.strip() for ln in m.group(1).splitlines() if ln.strip()
    ]
    zone = "\n".join(zone_lines)
    if zone == _normalize_newlines(code.strip()):
        print(f"OK：任务线装配生成区与目录一致（{path.name}）")
        return 0
    print(
        f"不一致：任务线装配生成区与当前目录生成的代码有差异（请运行 --write 更新）",
        file=sys.stderr,
    )
    return 1


# ── 专属节点方法生成区（orchestrator.py）：增量追加骨架 ─────

def write_nodes(path: Path, lines: list[str]) -> None:
    """向 orchestrator.py 的节点方法生成区追加缺失的骨架。

    已有实现（生成区内已有 ``async def _{线名}_{kind}_node``）的线跳过，
    不覆盖开发者填写的函数体；仅追加完全没有对应方法的线的骨架。
    """
    raw = _read_raw(path)
    if NODE_ZONE_START not in raw or NODE_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到专属节点方法生成区标记。请先手动添加：\n"
            f"{NODE_ZONE_START}\n（现有专属节点方法移入此处）\n{NODE_ZONE_END}"
        )
    m = re.search(_NODE_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中专属节点方法生成区标记不完整")
    zone = m.group(1)
    additions = []
    for line in lines:
        fn = f"_{line}_fallback_node"
        if f"async def {fn}" not in zone:
            additions.append(generate_node_skeleton(line))
    if not additions:
        print(f"无新增骨架：{path.name} 全部任务线已有降级节点方法")
        return
    nl = "\r\n" if "\r\n" in raw else "\n"
    new_zone = zone.rstrip("\r\n") + nl + nl + nl.join(additions) + nl
    block = (
        f"    {NODE_ZONE_START}"
        + nl
        + nl
        + new_zone
        + f"    {NODE_ZONE_END}"
    )
    new_raw = re.sub(
        _NODE_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已追加 {len(additions)} 个降级节点方法骨架到 {path}")


def check_nodes(path: Path, lines: list[str]) -> int:
    """校验每条线的 render/fallback 骨架签名都存在（不比较函数体）。"""
    raw = _read_raw(path)
    m = re.search(_NODE_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到专属节点方法生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    missing = []
    for line in lines:
        fn = f"_{line}_fallback_node"
        if f"async def {fn}" not in zone:
            missing.append(fn)
    if missing:
        print(f"缺失降级节点方法骨架: {missing}", file=sys.stderr)
        return 1
    print(f"OK：降级节点方法签名齐全（{len(lines)} 条线 × fallback）")
    return 0


# ── TASK_LINES 注册生成区（orchestrator.py）：整体替换 ───────

def write_task_lines(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的任务线注册生成区。"""
    raw = _read_raw(path)
    if TL_ZONE_START not in raw or TL_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到任务线注册生成区标记。请先手动添加：\n"
            f"{TL_ZONE_START}\n（现有 TASK_LINES 定义移入此处）\n{TL_ZONE_END}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_task_lines_code(lines).split("\n"))
    block = (
        TL_ZONE_START + nl + nl + code + nl + nl + TL_ZONE_END
    )
    new_raw = re.sub(
        _TL_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path} 任务线注册生成区")


def check_task_lines(path: Path, lines: list[str]) -> int:
    """校验任务线注册生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_TL_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到任务线注册生成区标记", file=sys.stderr)
        return 1
    # 保留行内缩进：只 strip 首尾空白，逐行比较前统一换行
    zone = _normalize_newlines(m.group(1)).strip()
    expected = _normalize_newlines(generate_task_lines_code(lines)).strip()
    if zone == expected:
        print(f"OK：任务线注册生成区与目录一致（{path.name}）")
        return 0
    print(
        f"不一致：任务线注册生成区与当前目录生成的代码有差异（请运行 --write 更新）",
        file=sys.stderr,
    )
    return 1


# ── __init__ 挂载生成区（orchestrator.py）：整体替换 ──────────

def write_mount(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的 Agent 挂载生成区。"""
    raw = _read_raw(path)
    if MOUNT_ZONE_START not in raw or MOUNT_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到 Agent 挂载生成区标记。请先手动添加：\n"
            f"{MOUNT_ZONE_START}\n（现有任务线挂载代码移入此处）\n{MOUNT_ZONE_END}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_mount_code(lines).split("\n"))
    block = (
        f"        {MOUNT_ZONE_START}"
        + nl
        + nl
        + code
        + nl
        + nl
        + f"        {MOUNT_ZONE_END}"
    )
    new_raw = re.sub(
        _MOUNT_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path} Agent 挂载生成区")


def check_mount(path: Path, lines: list[str]) -> int:
    """校验 Agent 挂载生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_MOUNT_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到 Agent 挂载生成区标记", file=sys.stderr)
        return 1
    zone = _normalize_newlines(m.group(1)).strip()
    expected = _normalize_newlines(generate_mount_code(lines)).strip()
    if zone == expected:
        print(f"OK：Agent 挂载生成区与目录一致（{path.name}）")
        return 0
    print(
        f"不一致：Agent 挂载生成区与当前目录生成的代码有差异（请运行 --write 更新）",
        file=sys.stderr,
    )
    return 1


# ── 节点映射生成区（orchestrator.py）：整体替换 ───────────────

def write_node_map(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的节点映射生成区（仅 _fallback_nodes）。"""
    raw = _read_raw(path)
    if NODEMAP_ZONE_START not in raw or NODEMAP_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到节点映射生成区标记。请先手动添加：\n"
            f"{NODEMAP_ZONE_START}\n（现有节点映射代码移入此处）\n{NODEMAP_ZONE_END}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = nl.join(generate_node_map_code(lines).split("\n"))
    block = (
        f"        {NODEMAP_ZONE_START}"
        + nl
        + nl
        + code
        + nl
        + nl
        + f"        {NODEMAP_ZONE_END}"
    )
    new_raw = re.sub(
        _NODEMAP_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path} 节点映射生成区")


def check_node_map(path: Path, lines: list[str]) -> int:
    """校验节点映射生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_NODEMAP_ZONE_PATTERN, raw, re.S)
    if m is None:
        print(f"{path.name} 中未找到节点映射生成区标记", file=sys.stderr)
        return 1
    zone = _normalize_newlines(m.group(1)).strip()
    expected = _normalize_newlines(generate_node_map_code(lines)).strip()
    if zone == expected:
        print(f"OK：节点映射生成区与目录一致（{path.name}）")
        return 0
    print(
        f"不一致：节点映射生成区与当前目录生成的代码有差异（请运行 --write 更新）",
        file=sys.stderr,
    )
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 tasks/ 目录生成任务线装配代码、TASK_LINES 注册、"
        "__init__ 挂载与节点映射、渲染上下文、专属节点方法骨架"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write",
        action="store_true",
        help="写入装配区 + TASK_LINES 区 + 挂载区 + 节点映射区 + 渲染上下文区 + 追加节点骨架",
    )
    group.add_argument("--check", action="store_true", help="校验全部生成区（CI 用）")
    args = parser.parse_args()

    lines = find_lines()
    code = generate_lines_code(lines)
    if args.write:
        _write_target(FACTORY_PATH, code)
        write_task_lines(ORCH_PATH, lines)
        write_mount(ORCH_PATH, lines)
        write_node_map(ORCH_PATH, lines)
        write_render_context(ORCH_PATH, lines)
        write_fallback_imports(ORCH_PATH, lines)
        write_report_imports(ORCH_PATH, lines)
        write_report_assemblers(ORCH_PATH, lines)
        write_fallback_rules(ORCH_PATH, lines)
        write_nodes(ORCH_PATH, lines)
    elif args.check:
        rc = _check_target(FACTORY_PATH, code)
        rc |= check_task_lines(ORCH_PATH, lines)
        rc |= check_mount(ORCH_PATH, lines)
        rc |= check_node_map(ORCH_PATH, lines)
        rc |= check_render_context(ORCH_PATH, lines)
        rc |= check_fallback_imports(ORCH_PATH, lines)
        rc |= check_report_imports(ORCH_PATH, lines)
        rc |= check_report_assemblers(ORCH_PATH, lines)
        rc |= check_fallback_rules(ORCH_PATH, lines)
        rc |= check_nodes(ORCH_PATH, lines)
        sys.exit(rc)
    else:
        print(f"发现任务线：{lines}\n")
        print("① 任务线装配代码（写入 create() 函数体生成区）：\n")
        for line in code.split("\n"):
            print(f"            {line}")
        print("\n② TASK_LINES 注册（写入 orchestrator.py 任务线注册生成区）：\n")
        print(generate_task_lines_code(lines))
        print("\n③ Agent 挂载（写入 orchestrator.py __init__ 挂载生成区）：\n")
        print(generate_mount_code(lines))
        print("\n④ 节点映射（写入 orchestrator.py __init__ 节点映射生成区）：\n")
        print(generate_node_map_code(lines))
        print("\n⑤ 渲染上下文（写入 orchestrator.py _Nodes 渲染上下文生成区）：\n")
        print(generate_render_context_code(lines))
        print("\n⑥ FallbackRules import（写入 orchestrator.py 顶部 import 生成区）：\n")
        print(generate_fallback_import_code(lines))
        print("\n⑦ Report import（写入 orchestrator.py 顶部 import 生成区）：\n")
        print(generate_report_import_code(lines))
        print("\n⑧ Report 组装器（写入 orchestrator.py __init__ 生成区）：\n")
        print(generate_report_assembler_code(lines))
        print("\n⑨ 专属节点方法骨架（写入 orchestrator.py 生成区，函数体由你填）：\n")
        print(generate_node_skeletons(lines))


if __name__ == "__main__":
    main()
