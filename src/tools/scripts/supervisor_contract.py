"""supervisor_contract.py —— 从输出契约自动生成审核模型代码。

读取 ``src/domain/meeting`` 下所有 ``*_OUTPUT_CONTRACT``，识别其中的
**审核模型契约**（顶层含 ``decision`` + ``feedback``，且含 ``{status, findings}``
形状的检查项），按统一模板生成对应的 dataclass + validate 代码。

设计：
- 契约是唯一来源：字段名、检查项、枚举值全部从契约解析
- **命名规范（强制）**：审核模型契约必须命名为
  ``{线名}_SUPERVISOR_OUTPUT_CONTRACT``，生成的类名为
  ``{线名}PascalCase`` + ``SupervisorReview``（不合规范直接报错）
- 语义规则（approve/revise/reject 联动）在 ``tools.validation.validate_supervisor_semantics``
  公共函数中，生成器只生成一行调用，不复制规则
- 业务输出模型（无 decision 的契约）会被识别并跳过（它们形状各异，暂不支持自动生成）

用法：
    python tools/scripts/supervisor_contract.py            # 生成并打印到 stdout
    python tools/scripts/supervisor_contract.py --write    # 写入 models.py 的审核模型生成区
    python tools/scripts/supervisor_contract.py --check    # 校验生成区与契约一致（CI 用，不一致退出码 1）

生成区标记（models.py 中）：
    # ── 审核模型生成区：由 tools/scripts/supervisor_contract.py 生成，勿手改 ──
    ...（生成的类）...
    # ── 审核模型生成区结束 ──
"""
from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

# 项目根（脚本位于 src/tools/scripts/supervisor_contract.py）
ROOT = Path(__file__).resolve().parents[3]
MEETING_DIR = ROOT / "src" / "domain" / "meeting"
MODELS_PATH = ROOT / "src" / "domain" / "meeting" / "models.py"
ORCH_PATH = ROOT / "src" / "domain" / "meeting" / "orchestrator.py"

# 审核模型生成区标记（models.py）
ZONE_START = "# ── 审核模型生成区：由 tools/scripts/supervisor_contract.py 生成，勿手改 ──"
ZONE_END = "# ── 审核模型生成区结束 ──"

# 拒绝审核常量生成区标记（orchestrator.py）
ZONE_REJECT_START = "# ── 拒绝审核常量生成区：由 tools/scripts/supervisor_contract.py 生成，勿手改 ──"
ZONE_REJECT_END = "# ── 拒绝审核常量生成区结束 ──"

# 任务线目录名 → 中文名（共享注册表 src/domain/meeting/line_registry.py；
# 新增任务线时在注册表补充，脚本与运行时共用同一份）
import sys as _sys

_sys.path.insert(0, str(ROOT / "src"))
from domain.meeting.line_registry import LINE_CN_NAMES  # noqa: E402
from tools.contracts import Check, SupervisorContract  # noqa: E402

# 审阅契约类名的强制后缀
CONTRACT_CLASS_SUFFIX = "SupervisorContract"


# ── 契约发现与解析 ──────────────────────────────────────────

def _import_module(path: Path):
    """按文件路径 import contracts.py 模块（模块名 = src 下的相对包路径）。"""
    rel = path.relative_to(ROOT / "src").with_suffix("")
    mod_name = ".".join(rel.parts)
    return importlib.import_module(mod_name)


def find_contracts() -> list[dict]:
    """遍历 meeting 下的 contracts.py，提取全部 SupervisorContract 子类。

    审阅契约类定义在各 {目录}/contracts.py；其输出模板常量
    （{基名大写}_SUPERVISOR_OUTPUT_CONTRACT）由同文件 to_json_template() 显式赋值，
    此处直接从类对象读结构（checks / decision / feedback）。
    """
    contracts = []
    for path in MEETING_DIR.rglob("contracts.py"):
        mod = _import_module(path)
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, SupervisorContract)
                and obj is not SupervisorContract
            ):
                contracts.append({"cls": obj, "path": path})
    return contracts


def _classify_contract(cls: type) -> dict:
    """从审阅契约类读取结构，返回 {fields: {键: 类型信息}}。

    类型信息：{"kind": "enum", "values": [...]} | {"kind": "check"} | {"kind": "str_list"}
    """
    checks = list(cls.checks)
    if not checks:
        raise ValueError(f"{cls.__name__} 缺少检查项（checks 列表为空）")
    fields: dict = {
        "decision": {"kind": "enum", "values": list(cls.decision.values)},
        "feedback": {"kind": "str_list"},
    }
    for ck in checks:
        if not isinstance(ck, Check):
            raise ValueError(f"{cls.__name__} 的 checks 元素必须是 Check 实例")
        fields[ck.name] = {"kind": "check"}
    return fields


def _review_class_name(cls: type) -> str:
    """审阅契约类 → 审核模型类名（MinutesSupervisorContract → MinutesSupervisorReview）。"""
    name = cls.__name__
    if not name.endswith(CONTRACT_CLASS_SUFFIX):
        raise ValueError(f"审阅契约类命名不符合规范：{name!r}")
    base = name[: -len(CONTRACT_CLASS_SUFFIX)]
    return f"{base}SupervisorReview"


def _cn_name(path: Path) -> str:
    """从契约所在目录推导中文名（tasks/{line_name}/contracts.py）。"""
    if "tasks" not in path.parts:
        return "任务"
    line_name = path.parts[path.parts.index("tasks") + 1]
    return LINE_CN_NAMES.get(line_name, line_name)


# ── 代码生成 ─────────────────────────────────────────────────

def generate_review_model(cls: str, cn_name: str, fields: dict) -> str:
    """按统一模板生成审核模型代码（与 models.py 现有手写版本逐字一致）。"""
    checks = [k for k, info in fields.items() if info["kind"] == "check"]
    if not checks:
        raise ValueError(f"{cls} 契约缺少检查项（{status,findings} 形状字段）")

    check_fields = "\n".join(f"    {k}: dict[str, Any]" for k in checks)
    check_keys = ", ".join(f'"{k}"' for k in checks)
    if len(checks) == 1:
        check_keys += ","  # 单元素 tuple 需要尾逗号

    return f"""@dataclass
class {cls}(ModelMixin):
    \"\"\"{cn_name}任务线的领域审核结果。\"\"\"

    decision: Literal["approve", "revise", "reject"]
{check_fields}
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ({check_keys})

    @classmethod
    def validate(cls, data: dict) -> "{cls}":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {{key: data[key] for key in cls.CHECK_KEYS}},
        )
        return cls(**data)"""


def _line_sort_key(contract: dict) -> int:
    """按 LINE_CN_NAMES 注册顺序排序（tasks/{线名}/contracts.py → 注册下标）。"""
    path = contract["path"]
    if "tasks" not in path.parts:
        return len(LINE_CN_NAMES)  # 非 tasks 目录的契约排最后
    line_name = path.parts[path.parts.index("tasks") + 1]
    if line_name in LINE_CN_NAMES:
        return list(LINE_CN_NAMES).index(line_name)
    return len(LINE_CN_NAMES)


def _upper_snake(cls: str) -> str:
    """PascalCase → UPPER_SNAKE（MinutesSupervisorReview → MINUTES_SUPERVISOR_REVIEW）。"""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls).upper()


def generate_reject_constants(cls: str, fields: dict) -> str:
    """从审核契约推导拒绝态兜底常量（_REJECT_{线名}_REVIEW）。

    模式：decision=reject；每个检查项 status=fail + 统一文案；feedback 固定文案。
    满足审核模型的校验约束（reject 时至少一个检查项失败）。
    """
    base = cls.removesuffix("SupervisorReview")  # MinutesSupervisorReview → Minutes
    name = "_REJECT_" + _upper_snake(base) + "_REVIEW"  # → _REJECT_MINUTES_REVIEW
    checks = [k for k, info in fields.items() if info["kind"] == "check"]
    if not checks:
        raise ValueError(f"{cls} 契约缺少检查项，无法生成拒绝态兜底")

    items = ['    "decision": "reject",']
    for ck in checks:
        items.append(
            f'    "{ck}": {{"status": "fail", "findings": ["LLM 调用失败，未完成审核"]}},'
        )
    items.append('    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],')
    body = "\n".join(items)
    return f"{name} = {{\n{body}\n}}"


def generate_all() -> tuple[str, str]:
    """生成全部审核模型代码与拒绝态兜底常量代码。

    返回 (models 代码, 拒绝态常量代码)。
    """
    generated = []
    reject_consts = []
    # 按任务线注册顺序输出（与 models.py 现有顺序一致，保证 diff 最小）
    for contract in sorted(find_contracts(), key=_line_sort_key):
        cls = contract["cls"]
        fields = _classify_contract(cls)
        review_cls = _review_class_name(cls)
        generated.append(
            generate_review_model(
                review_cls, _cn_name(contract["path"]), fields
            )
        )
        reject_consts.append(generate_reject_constants(review_cls, fields))
    if not generated:
        print("未发现审核模型契约", file=sys.stderr)
        return "", ""
    # 类之间空两行（PEP8 模块级类间距，与 models.py 现有格式一致）
    return "\n\n\n".join(generated), "\n\n".join(reject_consts)


# ── 写入 / 校验生成区（通用）────────────────────────────


def _read_raw(path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _zone_content(raw: str, start: str, end: str) -> str | None:
    # 兼容 CRLF / LF 及历史坏行尾（\r\r\n）：边界用 \r*\n
    m = re.search(
        re.escape(start) + r"\r*\n(.*?)\r*\n" + re.escape(end),
        raw,
        re.S,
    )
    return m.group(1).strip() if m else None


def _write_target(path, start: str, end: str, code: str, label: str) -> None:
    """把生成的代码写入指定文件的生成区（无标记则报错提示）。"""
    raw = _read_raw(path)
    if start not in raw or end not in raw:
        sys.exit(
            f"{path.name} 中未找到 {label} 生成区标记。请先手动添加：\n"
            f"{start}\n（现有内容移入此处）\n{end}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    # 先按 \n 拼装（避免 \r\n 被二次替换），再统一转为文件行尾
    gen_block = nl.join(code.split("\n"))
    block = start + nl + nl + gen_block + nl + nl + nl + end
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


def _check_target(path, start: str, end: str, code: str, label: str) -> int:
    """校验生成区与当前契约生成的代码一致；一致返回 0，否则返回 1。"""
    zone = _zone_content(_read_raw(path), start, end)
    if zone is None:
        print(f"{path.name} 中未找到 {label} 生成区标记", file=sys.stderr)
        return 1
    if _normalize_newlines(zone) == _normalize_newlines(code.strip()):
        print(f"OK：{label}生成区与契约一致")
        return 0
    print(f"不一致：{label}生成区与当前契约生成的代码有差异（请运行 --write 更新）", file=sys.stderr)
    return 1


# 两个生成目标：models.py 的审核模型区 + orchestrator.py 的拒绝审核常量区
_TARGETS = [
    (MODELS_PATH, ZONE_START, ZONE_END, "审核模型"),
    (ORCH_PATH, ZONE_REJECT_START, ZONE_REJECT_END, "拒绝审核常量"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="从审阅契约生成审核模型 + 拒绝态兜底常量")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="写入全部生成区")
    group.add_argument("--check", action="store_true", help="校验全部生成区与契约一致（CI 用）")
    args = parser.parse_args()

    models_code, reject_code = generate_all()
    if args.write:
        for path, start, end, label in _TARGETS:
            code = models_code if label == "审核模型" else reject_code
            _write_target(path, start, end, code, label)
    elif args.check:
        rc = 0
        for path, start, end, label in _TARGETS:
            code = models_code if label == "审核模型" else reject_code
            rc |= _check_target(path, start, end, code, label)
        sys.exit(rc)
    else:
        print(models_code)
        if reject_code:
            print("\n# ── 拒绝态兜底常量（写入 orchestrator.py）──\n")
            print(reject_code)


if __name__ == "__main__":
    main()
