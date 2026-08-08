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

# 节点映射生成区标记（orchestrator.py 的 __init__ 内，_render_nodes/_fallback_nodes）
NODEMAP_ZONE_START = "# ── 节点映射生成区：由 tools/scripts/factory_contract.py 生成，勿手改 ──"
NODEMAP_ZONE_END = "# ── 节点映射生成区结束 ──"

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


def generate_node_skeleton(line: str, kind: str) -> str:
    """生成单线单方法的专属节点骨架（签名 + 占位注释 + 默认兜底 return）。

    kind ∈ {"render", "fallback"}；行首带 4 空格类内缩进。
    默认 return 保证未实现时也能运行（空输出 + degraded 降级标记），
    开发者实现逻辑后应替换/前置 return。
    """
    fn = f"_{line}_{kind}_node"
    if kind == "render":
        hint = (
            f"        ## 这里新增你的代码：渲染{line}线（写入 "
            f'lines["{line}"]["rendered"]）'
        )
        default = (
            f'        return {{"lines": {{"{line}": {{"rendered": "", '
            f'"degraded": True}}}}, "quality_degraded": True}}'
        )
    else:
        hint = (
            f"        ## 这里新增你的代码：降级输出（写入 "
            f'lines["{line}"]["rendered"] + degraded）'
        )
        default = (
            f'        return {{"lines": {{"{line}": {{"rendered": "（降级）", '
            f'"degraded": True}}}}, "quality_degraded": True}}'
        )
    return (
        f"    async def {fn}(self, state: MeetingState) -> dict:\n"
        f"{hint}\n"
        f"        ## 未实现时返回空降级兜底（保证可运行）；实现后请替换下方 return\n"
        f"{default}\n"
    )


def generate_node_skeletons(lines: list[str]) -> str:
    """生成全部线的专属节点方法骨架（render + fallback，按线排序）。"""
    blocks = []
    for line in lines:
        blocks.append(generate_node_skeleton(line, "render"))
        blocks.append(generate_node_skeleton(line, "fallback"))
    return "\n".join(blocks)


# ── TASK_LINES 注册生成 ──────────────────────────────────────

def _contract_base(line: str, tasks_dir: Path | None = None) -> str:
    """线名 → 契约基名：解析该线 prompts.py 的生成契约名，去后缀。

    例：minutes_generation/prompts.py 里 MINUTES_GENERATION_OUTPUT_CONTRACT
    → 返回 "MINUTES"（用于推导 _EMPTY_MINUTES / _REJECT_MINUTES_REVIEW）。
    """
    tasks_dir = tasks_dir or TASKS_DIR
    prompts_path = tasks_dir / line / "prompts.py"
    if not prompts_path.exists():
        raise ValueError(f"{prompts_path} 不存在（无法解析生成契约）")
    tree = ast.parse(prompts_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            name = node.targets[0].id
            if name.endswith("_GENERATION_OUTPUT_CONTRACT"):
                return name.removesuffix("_GENERATION_OUTPUT_CONTRACT")
    raise ValueError(
        f"{prompts_path} 未找到 *_GENERATION_OUTPUT_CONTRACT 生成契约"
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
    """生成 __init__ 的渲染/降级节点映射（{} + 追加式，行首 8 空格缩进）。

    _render_nodes / _fallback_nodes 每行完全同构：
    ``self._render_nodes["{line}"] = self._{line}_render_node``
    """
    blocks = ["        self._render_nodes: dict[str, object] = {}"]
    blocks += [
        f'        self._render_nodes["{line}"] = self._{line}_render_node'
        for line in lines
    ]
    blocks.append("        self._fallback_nodes: dict[str, object] = {}")
    blocks += [
        f'        self._fallback_nodes["{line}"] = self._{line}_fallback_node'
        for line in lines
    ]
    return "\n".join(blocks)


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
        for kind in ("render", "fallback"):
            fn = f"_{line}_{kind}_node"
            if f"async def {fn}" not in zone:
                additions.append(generate_node_skeleton(line, kind))
    if not additions:
        print(f"无新增骨架：{path.name} 全部任务线已有专属节点方法")
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
    print(f"已追加 {len(additions)} 个专属节点方法骨架到 {path}")


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
        for kind in ("render", "fallback"):
            fn = f"_{line}_{kind}_node"
            if f"async def {fn}" not in zone:
                missing.append(fn)
    if missing:
        print(f"缺失专属节点方法骨架: {missing}", file=sys.stderr)
        return 1
    print(f"OK：专属节点方法签名齐全（{len(lines)} 条线 × render/fallback）")
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
    """整体重写 orchestrator.py 的节点映射生成区（_render_nodes/_fallback_nodes）。"""
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
        "__init__ 挂载与节点映射、专属节点方法骨架"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write",
        action="store_true",
        help="写入装配区 + TASK_LINES 区 + 挂载区 + 节点映射区 + 追加节点骨架",
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
        write_nodes(ORCH_PATH, lines)
    elif args.check:
        rc = _check_target(FACTORY_PATH, code)
        rc |= check_task_lines(ORCH_PATH, lines)
        rc |= check_mount(ORCH_PATH, lines)
        rc |= check_node_map(ORCH_PATH, lines)
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
        print("\n⑤ 专属节点方法骨架（写入 orchestrator.py 生成区，函数体由你填）：\n")
        print(generate_node_skeletons(lines))


if __name__ == "__main__":
    main()
