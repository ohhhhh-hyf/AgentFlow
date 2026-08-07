"""generation_contract.py —— 从生成契约自动生成浅校验模型代码。

读取 ``src/domain/meeting`` 下所有以 ``_GENERATION_OUTPUT_CONTRACT`` 结尾的
生成契约（core 的会议理解/视角建模 + task 的纪要/待办产物），按统一模板
生成对应的 dataclass + **浅校验** validate 代码。

浅校验说明：
- 只校验**第一层**：键齐全（_exact_fields）+ 第一层类型（字符串/数组/枚举）
- **嵌套不校验**：数组元素内部（如待办条目的 7 字段）不逐条检查，
  深层结构问题由下游 supervisor 审核与 SchemaRepair 兜底
- 因此任何形状的生成契约都能机械推导，无需手写嵌套校验规则

命名规范（强制）：契约必须命名为 ``{线名/功能}_GENERATION_OUTPUT_CONTRACT``，
生成的类名为 ``{线名/功能}PascalCase``（截掉后缀、蛇形转大驼峰）。

用法：
    python tools/scripts/generation_contract.py            # 生成并打印
    python tools/scripts/generation_contract.py --write    # 写入 models.py 的生成模型生成区
    python tools/scripts/generation_contract.py --check    # 校验生成区与契约一致（CI 用）

生成区标记（models.py 中）：
    # ── 生成模型生成区：由 tools/scripts/generation_contract.py 生成，勿手改 ──
    ...（生成的类）...
    # ── 生成模型生成区结束 ──
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# 项目根（脚本位于 src/tools/scripts/generation_contract.py）
ROOT = Path(__file__).resolve().parents[3]
MEETING_DIR = ROOT / "src" / "domain" / "meeting"
MODELS_PATH = ROOT / "src" / "domain" / "meeting" / "models.py"
ORCH_PATH = ROOT / "src" / "domain" / "meeting" / "orchestrator.py"

# 生成模型生成区标记（models.py）
ZONE_START = "# ── 生成模型生成区：由 tools/scripts/generation_contract.py 生成，勿手改 ──"
ZONE_END = "# ── 生成模型生成区结束 ──"

# 空结构常量生成区标记（orchestrator.py）
ZONE_EMPTY_START = "# ── 空结构常量生成区：由 tools/scripts/generation_contract.py 生成，勿手改 ──"
ZONE_EMPTY_END = "# ── 空结构常量生成区结束 ──"

# 生成契约的强制命名后缀
GENERATION_CONTRACT_SUFFIX = "_GENERATION_OUTPUT_CONTRACT"

# 生成契约 → 中文名（用于 docstring；新增生成契约时在此补充）
GENERATION_CN_NAMES = {
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT": "会议理解",
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT": "视角建模",
    "MINUTES_GENERATION_OUTPUT_CONTRACT": "纪要草稿",
    "ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT": "待办提取",
}


# ── 契约发现 ──────────────────────────────────────────────────

def find_contracts() -> list[dict]:
    """遍历 meeting 下的 prompts.py，提取全部 *_GENERATION_OUTPUT_CONTRACT 常量。"""
    contracts = []
    for path in MEETING_DIR.rglob("prompts.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            name = node.targets[0].id
            if not name.endswith(GENERATION_CONTRACT_SUFFIX):
                continue
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                continue
            contracts.append({
                "name": name,
                "text": node.value.value,
                "path": path,
            })
    return contracts


# ── 字段类型推断（浅层）──────────────────────────────────────

def parse_generation_contract(text: str) -> list[dict]:
    """解析生成契约，推导第一层每个字段的类型信息。

    返回有序列表：[{key, kind, values?}]；
    kind ∈ {"str", "str_null", "enum", "str_list", "obj_list", "dict"}。
    推断规则（浅层、启发式）：
    - 字符串值：含 "|" → 枚举；含 "null" → 可空字符串；否则字符串
    - 数组值：首元素为 dict → 对象数组；首元素为 str → 字符串数组；
      空数组 → 保守推断对象数组（现有契约的空数组均为对象数组）
    - 字典值 → dict（防御，现有生成契约顶层无此形状）
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"契约不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("契约顶层必须是 JSON 对象")

    fields = []
    for key, value in data.items():
        if isinstance(value, str):
            if "|" in value:
                fields.append({
                    "key": key,
                    "kind": "enum",
                    "values": [v.strip() for v in value.split("|")],
                })
            elif "null" in value:
                fields.append({"key": key, "kind": "str_null"})
            else:
                fields.append({"key": key, "kind": "str"})
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                fields.append({"key": key, "kind": "obj_list"})
            elif value and isinstance(value[0], str):
                fields.append({"key": key, "kind": "str_list"})
            else:
                fields.append({"key": key, "kind": "obj_list"})  # 空数组
        elif isinstance(value, dict):
            fields.append({"key": key, "kind": "dict"})
        else:
            raise ValueError(
                f"生成契约含无法推导的字段：{key}={value!r}"
                "（仅支持字符串/枚举/数组/对象）"
            )
    return fields


# ── 命名 ──────────────────────────────────────────────────────

def generation_class_name(contract_name: str) -> str:
    """生成契约名 → 类名。

    命名规范（强制）：契约必须命名为 ``{线名/功能}_GENERATION_OUTPUT_CONTRACT``，
    生成的类名为 ``{线名/功能}PascalCase``。

    例：
        MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT → MeetingUnderstanding
        MINUTES_GENERATION_OUTPUT_CONTRACT              → Minutes
        ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT         → ActionItems
    """
    if not contract_name.endswith(GENERATION_CONTRACT_SUFFIX):
        raise ValueError(
            f"生成契约命名不符合规范：{contract_name!r}\n"
            f"必须命名为 {{线名/功能}}{GENERATION_CONTRACT_SUFFIX}"
        )
    base = contract_name.removesuffix(GENERATION_CONTRACT_SUFFIX)
    return "".join(part.capitalize() for part in base.split("_"))


# ── 代码生成（浅校验模板）────────────────────────────────────

def _field_declaration(field: dict) -> str:
    """dataclass 字段声明行。"""
    key, kind = field["key"], field["kind"]
    if kind == "str":
        return f"    {key}: str"
    if kind == "str_null":
        return f"    {key}: str | None = None"
    if kind == "enum":
        values = ", ".join(f'"{v}"' for v in field["values"])
        return f"    {key}: Literal[{values}]"
    if kind == "str_list":
        return f"    {key}: list[str] = field(default_factory=list)"
    if kind == "obj_list":
        return f"    {key}: list[dict[str, Any]] = field(default_factory=list)"
    if kind == "dict":
        return f"    {key}: dict[str, Any] = field(default_factory=dict)"
    raise ValueError(f"未知字段类型：{kind}")


def _validation_line(field: dict) -> str:
    """validate 中的第一层类型检查行。"""
    key, kind = field["key"], field["kind"]
    if kind == "str":
        return f'        _string(data["{key}"], "{key}")'
    if kind == "str_null":
        return f'        _string(data["{key}"], "{key}", nullable=True)'
    if kind == "enum":
        values = ", ".join(f'"{v}"' for v in field["values"])
        return f'        _choice(data["{key}"], {{{values}}}, "{key}")'
    if kind == "str_list":
        return f'        _string_list(data["{key}"], "{key}")'
    if kind in ("obj_list", "dict"):
        noun = "数组" if kind == "obj_list" else "对象"
        return (
            f'        if not isinstance(data["{key}"], list):\n'
            f'            raise OutputValidationError("{key} 必须是{noun}")'
        ) if kind == "obj_list" else (
            f'        if not isinstance(data["{key}"], dict):\n'
            f'            raise OutputValidationError("{key} 必须是{noun}")'
        )
    raise ValueError(f"未知字段类型：{kind}")


def generate_generation_model(cls: str, cn_name: str, fields: list[dict]) -> str:
    """按浅校验模板生成模型代码。

    字段按 dataclass 规则排序：无默认值的字段（str/enum）在前，
    有默认值的字段（list/可空）在后，避免 non-default-after-default 报错。
    """
    has_default = {"str_null", "str_list", "obj_list", "dict"}
    ordered = sorted(fields, key=lambda f: f["kind"] in has_default)

    field_lines = "\n".join(_field_declaration(f) for f in ordered)
    check_lines = "\n".join(_validation_line(f) for f in ordered)

    return f"""@dataclass
class {cls}(ModelMixin):
    \"\"\"{cn_name}输出（浅校验：仅校验第一层键与类型，嵌套不校验）。\"\"\"

{field_lines}

    @classmethod
    def validate(cls, data: dict) -> "{cls}":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
{check_lines}
        return cls(**data)"""


def _upper_snake(cls: str) -> str:
    """PascalCase → UPPER_SNAKE（MeetingUnderstanding → MEETING_UNDERSTANDING）。"""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls).upper()


def generate_empty_constants(cls: str, fields: list[dict]) -> str:
    """从生成契约推导最小空结构常量（_EMPTY_{CLS}）。

    类型 → 空值映射：str → ""；str|null → None；枚举 → 契约第一个值；
    字符串/对象数组 → []；对象 → {}。
    """
    name = "_EMPTY_" + _upper_snake(cls)
    items = []
    for f in fields:
        key = f["key"]
        if f["kind"] == "str":
            items.append(f'    "{key}": "",')
        elif f["kind"] == "str_null":
            items.append(f'    "{key}": None,')
        elif f["kind"] == "enum":
            items.append(f'    "{key}": "{f["values"][0]}",')
        elif f["kind"] in ("str_list", "obj_list"):
            items.append(f'    "{key}": [],')
        elif f["kind"] == "dict":
            items.append(f'    "{key}": {{}},')
        else:
            raise ValueError(f"未知字段类型：{f['kind']}")
    body = "\n".join(items)
    return f'{name} = {{\n{body}\n}}'


def generate_all() -> tuple[str, str]:
    """生成全部生成契约模型代码与空结构常量代码。

    返回 (models 代码, 空结构常量代码)。
    """
    generated = []
    empty_consts = []
    for contract in sorted(find_contracts(), key=lambda c: c["name"]):
        fields = parse_generation_contract(contract["text"])
        cls = generation_class_name(contract["name"])
        cn = GENERATION_CN_NAMES.get(contract["name"], cls)
        generated.append(generate_generation_model(cls, cn, fields))
        empty_consts.append(generate_empty_constants(cls, fields))
    if not generated:
        print("未发现生成契约", file=sys.stderr)
        return "", ""
    return "\n\n\n".join(generated), "\n\n".join(empty_consts)


# ── 写入 / 校验生成区（通用）────────────────────────────


def _read_raw(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _zone_content(raw: str, start: str, end: str) -> str | None:
    m = re.search(
        re.escape(start) + r"\r*\n(.*?)\r*\n" + re.escape(end),
        raw,
        re.S,
    )
    return m.group(1).strip() if m else None


def _write_target(path: Path, start: str, end: str, code: str, label: str) -> None:
    """把生成的代码写入指定文件的生成区（无标记则报错提示）。"""
    raw = _read_raw(path)
    if start not in raw or end not in raw:
        sys.exit(
            f"{path.name} 中未找到 {label} 生成区标记。请先手动添加：\n"
            f"{start}\n（现有内容移入此处）\n{end}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    code_block = nl.join(code.split("\n"))
    block = start + nl + nl + code_block + nl + nl + nl + end
    new_raw = re.sub(
        re.escape(start) + r"\r*\n.*?\r*\n" + re.escape(end),
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    print(f"已写入 {path}")


def _normalize_newlines(text: str) -> str:
    """统一行尾为 \\n（用于内容比较，与文件实际行尾无关）。"""
    return re.sub(r"\r*\n", "\n", text)


def _check_target(path: Path, start: str, end: str, code: str, label: str) -> int:
    """校验生成区与契约一致；一致返回 0，否则返回 1。"""
    zone = _zone_content(_read_raw(path), start, end)
    if zone is None:
        print(f"{path.name} 中未找到 {label} 生成区标记", file=sys.stderr)
        return 1
    if _normalize_newlines(zone) == _normalize_newlines(code.strip()):
        print(f"OK：{label}生成区与契约一致")
        return 0
    print(f"不一致：{label}生成区与当前契约生成的代码有差异（请运行 --write 更新）", file=sys.stderr)
    return 1


# 两个生成目标：models.py 的生成模型区 + orchestrator.py 的空结构常量区
_TARGETS = [
    (MODELS_PATH, ZONE_START, ZONE_END, "生成模型"),
    (ORCH_PATH, ZONE_EMPTY_START, ZONE_EMPTY_END, "空结构常量"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="从生成契约生成浅校验模型 + 空结构常量")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="写入全部生成区")
    group.add_argument("--check", action="store_true", help="校验全部生成区与契约一致（CI 用）")
    args = parser.parse_args()

    models_code, empty_code = generate_all()
    if args.write:
        for path, start, end, label in _TARGETS:
            code = models_code if label == "生成模型" else empty_code
            _write_target(path, start, end, code, label)
    elif args.check:
        rc = 0
        for path, start, end, label in _TARGETS:
            code = models_code if label == "生成模型" else empty_code
            rc |= _check_target(path, start, end, code, label)
        sys.exit(rc)
    else:
        print(models_code)
        if empty_code:
            print("\n# ── 空结构常量（写入 orchestrator.py）──\n")
            print(empty_code)


if __name__ == "__main__":
    main()
