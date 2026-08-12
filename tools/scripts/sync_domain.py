"""sync_domain.py —— 一次生成全部契约生成区的唯一脚本入口。

新增任务线只需：

    python sync_domain.py --write     # 一次生成全部生成区
    python sync_domain.py --check     # 一次校验全部生成区（CI 用）

内部按三段执行（原三个独立脚本的合并体，职责分段清晰）：

    # ── 段① 生成契约 ── 生成业务模型（浅校验）+ 空结构常量
    # ── 段② 审阅契约 ── 审核模型（深校验）+ 拒绝态常量
    # ── 段③ 装配/注册 ─ 装配 / TASK_LINES / 挂载 / 节点映射 /
    #                  渲染上下文 / import / Report 组装器 /
    #                  FallbackRules 注册 / fallback 节点
"""

from __future__ import annotations

import argparse
import ast
import importlib
import re
import sys
import traceback
from pathlib import Path

# 项目根（脚本位于 tools/scripts/sync_domain.py）
ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))


def _log(*args, **kwargs) -> None:
    """静默日志：成功/校验细节不输出；命令结尾统一输出 SUCCESS! / FAIL!!!。"""
    return None


def _info(message: str) -> None:
    print(message)


def _read_py(path: Path) -> str:
    """读取 Python 源码，兼容 Windows 工具写入的 UTF-8 BOM。"""
    return path.read_text(encoding="utf-8-sig")


def _compact_blank_lines(text: str) -> str:
    """Normalize line endings and collapse excessive blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    blank_count = sum(1 for line in lines if not line.strip())
    nonblank_count = max(1, len(lines) - blank_count)
    if blank_count > nonblank_count * 0.6:
        text = "\n".join(line for line in lines if line.strip())
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text


from tools.contracts import (  # noqa: E402
    GenerationContract,
    SupervisorContract,
)


# ── 领域上下文：路径 / 配置由 --domain 推导，脚本不再硬编码任何领域 ──

def _pascal_name(name: str) -> str:
    """领域名 → PascalCase（meeting → Meeting；notes → Notes）。"""
    return name[0].upper() + name[1:]


class _Domain:
    """当前目标领域：路径 + 配置全部由此推导/懒加载。

    配置从 ``domain/<name>/domain_config.py`` 读取（STATE_CLASS /
    RENDER_CONTEXT_STATE_LINES）；中文名注册表从
    ``domain/<name>/domain_config.py`` 读取（LINE_CN_NAMES）。
    """

    def __init__(self, name: str):
        self.name = name
        self.dir = ROOT / "domain" / name
        self.tasks_dir = self.dir / "tasks"
        self.factory_path = self.dir / f"{name}_factory.py"
        self.reports_path = self.dir / "reports.py"
        self.models_path = self.dir / "models.py"
        self.orch_path = self.dir / "orchestrator.py"
        self._config: dict | None = None
        self._cn_names: dict | None = None

    def config(self) -> dict:
        if self._config is None:
            path = self.dir / "domain_config.py"
            cfg = {
                "STATE_CLASS": _pascal_name(self.name) + "State",
                "RENDER_CONTEXT_STATE_LINES": [],
            }
            if path.exists():
                tree = ast.parse(_read_py(path))
                for node in tree.body:
                    if (
                        isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id
                        in ("STATE_CLASS", "RENDER_CONTEXT_STATE_LINES")
                    ):
                        try:
                            val = ast.literal_eval(node.value)
                            if val:
                                cfg[node.targets[0].id] = val
                        except Exception:
                            pass
            self._config = {
                "STATE_CLASS": cfg["STATE_CLASS"],
                "RENDER_CONTEXT_STATE_LINES": cfg["RENDER_CONTEXT_STATE_LINES"],
            }
        return self._config

    def state_class(self) -> str:
        return self.config()["STATE_CLASS"]

    def render_context_state_lines(self) -> list[str]:
        return self.config()["RENDER_CONTEXT_STATE_LINES"]

    def line_cn_names(self) -> dict:
        if self._cn_names is None:
            path = self.dir / "domain_config.py"
            if not path.exists():
                raise SystemExit(f"{path} 不存在——请先创建领域骨架（含 domain_config.py）")
            tree = ast.parse(_read_py(path))
            found = None
            for node in tree.body:
                if (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == "LINE_CN_NAMES"
                ):
                    found = ast.literal_eval(node.value)
                    break
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "LINE_CN_NAMES"
                ):
                    found = ast.literal_eval(node.value)
                    break
            if not isinstance(found, dict):
                raise SystemExit(f"{path} 未找到 LINE_CN_NAMES dict 定义")
            self._cn_names = found
        return self._cn_names


CURRENT = _Domain("meeting")  # 默认领域；main 里按 --domain 切换


def set_domain(name: str) -> None:
    """切换当前领域（--domain <name>）。"""
    global CURRENT
    CURRENT = _Domain(name)


GEN_ZONE_START = "# ── 生成模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
GEN_ZONE_END = "# ── 生成模型生成区结束 ──"

# 空结构常量生成区标记（orchestrator.py）
GEN_ZONE_EMPTY_START = "# ── 空结构常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
GEN_ZONE_EMPTY_END = "# ── 空结构常量生成区结束 ──"

# 生成契约的强制命名后缀（类名约定）
GENERATION_CLASS_SUFFIX = "GenerationContract"

sys.path.insert(0, str(ROOT))
from tools.contracts import GenerationContract  # noqa: E402


# ── 契约发现 ──────────────────────────────────────────────────

def _load_module_file(path: Path):
    """按文件路径直接加载模块（绕过包 __init__ 链）。

    脚本只读契约声明，不应 import 领域包——domain/meeting/__init__.py 会连锁
    import models.py，而 models.py 顶层依赖生成的 mixin（鸡生蛋）。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载模块：{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def find_gen_contracts() -> list[dict]:
    """遍历当前 domain 下的 contracts.py，提取全部 GenerationContract 子类。

    生成契约类定义在各 {目录}/contracts.py；其输出模板常量
    （{基名大写}_GENERATION_OUTPUT_CONTRACT）由同文件 to_json_template() 显式赋值，
    此处直接从类对象读字段结构。
    """
    contracts = []
    for path in CURRENT.dir.rglob("contracts.py"):
        mod = _load_module_file(path)
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, GenerationContract)
                and obj is not GenerationContract
            ):
                contracts.append({"cls": obj, "path": path})
    return contracts


# ── 字段类型推断（浅层）──────────────────────────────────────

def parse_generation_contract(cls: type) -> list[dict]:
    """从生成契约类读取字段结构，推导第一层每个字段的类型信息。

    返回有序列表：[{key, kind, values?}]；
    kind ∈ {"str", "enum", "str_list", "obj_list", "dict"}。
    与旧版 JSON 解析产出的结构一致（生成逻辑无需改动）。
    """
    fields = []
    for f in cls.fields:
        entry: dict = {"key": f.name, "kind": f.kind}
        if f.kind == "enum":
            entry["values"] = list(f.values)
        fields.append(entry)
    return fields


# ── 命名 ──────────────────────────────────────────────────────

def generation_class_name(cls: type) -> str:
    """生成契约类 → 模型类名。

    命名规范（强制）：类必须命名为 ``{线名/功能}GenerationContract``，
    生成的模型类名为 ``{线名/功能}PascalCase``（去 GenerationContract 后缀）。

    例：
        MeetingUnderstandingGenerationContract → MeetingUnderstanding
        MinutesGenerationContract            → Minutes
        ActionItemsGenerationContract        → ActionItems
    """
    name = cls.__name__
    if not name.endswith(GENERATION_CLASS_SUFFIX):
        raise ValueError(
            f"生成契约类命名不符合规范：{name!r}\n"
            f"必须命名为 {{线名/功能}}{GENERATION_CLASS_SUFFIX}"
        )
    return name.removesuffix(GENERATION_CLASS_SUFFIX)


# ── 代码生成（浅校验模板）────────────────────────────────────

def _field_declaration(field: dict) -> str:
    """dataclass 字段声明行。"""
    key, kind = field["key"], field["kind"]
    if kind == "str":
        return f"    {key}: str"
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


def generate_generation_model(cls: str, fields: list[dict]) -> str:
    """按浅校验模板生成模型代码。

    字段按 dataclass 规则排序：无默认值的字段（str/enum）在前，
    有默认值的字段（list/可空）在后，避免 non-default-after-default 报错。
    """
    has_default = {"str_list", "obj_list", "dict"}
    ordered = sorted(fields, key=lambda f: f["kind"] in has_default)

    field_lines = "\n".join(_field_declaration(f) for f in ordered)
    check_lines = "\n".join(_validation_line(f) for f in ordered)

    return f"""@dataclass
class {cls}(ModelMixin):
    \"\"\"{cls}输出（浅校验：仅校验第一层键与类型，嵌套不校验）。\"\"\"

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
    structure = []
    for f in fields:
        key = f["key"]
        if f["kind"] == "str":
            structure.append(f'    "{key}": "",')
        elif f["kind"] == "enum":
            structure.append(f'    "{key}": "{f["values"][0]}",')
        elif f["kind"] in ("str_list", "obj_list"):
            structure.append(f'    "{key}": [],')
        elif f["kind"] == "dict":
            structure.append(f'    "{key}": {{}},')
        else:
            raise ValueError(f"未知字段类型：{f['kind']}")
    body = "\n".join(structure)
    return f'{name} = {{\n{body}\n}}'


def gen_generate_all() -> tuple[str, str]:
    """生成全部生成契约模型代码与空结构常量代码。

    返回 (models 代码, 空结构常量代码)。
    """
    generated = []
    empty_consts = []
    for contract in sorted(find_gen_contracts(), key=lambda c: c["cls"].__name__):
        cls = contract["cls"]
        fields = parse_generation_contract(cls)
        model_cls = generation_class_name(cls)
        generated.append(generate_generation_model(model_cls, fields))
        empty_consts.append(generate_empty_constants(model_cls, fields))
    if not generated:
        _log("未发现生成契约", file=sys.stderr)
        return "", ""
    return "\n\n\n".join(generated), "\n\n".join(empty_consts)


# ── 写入 / 校验生成区（通用）────────────────────────────


def _read_raw(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return _compact_blank_lines(fh.read())


def _gen_zone_content(raw: str, start: str, end: str) -> str | None:
    m = re.search(
        re.escape(start) + r"\r*\n(.*?)\r*\n" + re.escape(end),
        raw,
        re.S,
    )
    return m.group(1).strip() if m else None


def _gen_write_target(path: Path, start: str, end: str, code: str, label: str) -> None:
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
    _log(f"已写入 {path}")


def _normalize_newlines(text: str) -> str:
    """统一行尾为 \\n（用于内容比较，与文件实际行尾无关）。"""
    return _compact_blank_lines(re.sub(r"\r*\n", "\n", text)).strip()


def _gen_check_target(path: Path, start: str, end: str, code: str, label: str) -> int:
    """校验生成区与契约一致；一致返回 0，否则返回 1。"""
    zone = _gen_zone_content(_read_raw(path), start, end)
    if zone is None:
        _log(f"{path.name} 中未找到 {label} 生成区标记", file=sys.stderr)
        return 1
    if _normalize_newlines(zone) == _normalize_newlines(code):
        _log(f"OK：{label}生成区与契约一致")
        return 0
    _log(f"不一致：{label}生成区与当前契约生成的代码有差异（请运行 --write 更新）", file=sys.stderr)
    return 1


# 两个生成目标：models.py 的生成模型区 + orchestrator.py 的空结构常量区
def _gen_targets() -> list[tuple]:
    return [
        (CURRENT.models_path, GEN_ZONE_START, GEN_ZONE_END, "生成模型"),
        (CURRENT.orch_path, GEN_ZONE_EMPTY_START, GEN_ZONE_EMPTY_END, "空结构常量"),
    ]


SUP_ZONE_START = "# ── 审核模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
SUP_ZONE_END = "# ── 审核模型生成区结束 ──"

# 拒绝审核常量生成区标记（orchestrator.py）
SUP_ZONE_REJECT_START = "# ── 拒绝审核常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
SUP_ZONE_REJECT_END = "# ── 拒绝审核常量生成区结束 ──"

# 任务线目录名 → 中文名（共享注册表 domain/<name>/domain_config.py；
# 新增任务线时在注册表补充，脚本与运行时共用同一份；由 _Domain.line_cn_names() 动态加载）
from tools.contracts import Check, SupervisorContract  # noqa: E402

# 审阅契约类名的强制后缀
CONTRACT_CLASS_SUFFIX = "SupervisorContract"


# ── 契约发现与解析 ──────────────────────────────────────────

def _sup_import_module(path: Path):
    """按文件路径直接加载 contracts.py（绕过包 __init__ 链）。"""
    return _load_module_file(path)


def find_sup_contracts() -> list[dict]:
    """遍历当前 domain 下的 contracts.py，提取全部 SupervisorContract 子类。

    审阅契约类定义在各 {目录}/contracts.py；其输出模板常量
    （{基名大写}_SUPERVISOR_OUTPUT_CONTRACT）由同文件 to_json_template() 显式赋值，
    此处直接从类对象读结构（checks / decision / feedback）。
    """
    contracts = []
    for path in CURRENT.dir.rglob("contracts.py"):
        mod = _sup_import_module(path)
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, SupervisorContract)
                and obj is not SupervisorContract
            ):
                contracts.append({"cls": obj, "path": path})
    return contracts


def _sup_classify_contract(cls: type) -> dict:
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


def _sup_review_class_name(cls: type) -> str:
    """审阅契约类 → 审核模型类名（MinutesSupervisorContract → MinutesSupervisorReview）。"""
    name = cls.__name__
    if not name.endswith(CONTRACT_CLASS_SUFFIX):
        raise ValueError(f"审阅契约类命名不符合规范：{name!r}")
    base = name[: -len(CONTRACT_CLASS_SUFFIX)]
    return f"{base}SupervisorReview"


def _sup_cn_name(path: Path) -> str:
    """从契约所在目录推导中文名（tasks/{line_name}/contracts.py）。"""
    if "tasks" not in path.parts:
        return "任务"
    line_name = path.parts[path.parts.index("tasks") + 1]
    return CURRENT.line_cn_names().get(line_name, line_name)


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


def _sup_line_sort_key(contract: dict) -> int:
    """按 LINE_CN_NAMES 注册顺序排序（tasks/{线名}/contracts.py → 注册下标）。"""
    path = contract["path"]
    line_cn = CURRENT.line_cn_names()
    if "tasks" not in path.parts:
        return len(line_cn)  # 非 tasks 目录的契约排最后
    line_name = path.parts[path.parts.index("tasks") + 1]
    if line_name in line_cn:
        return list(line_cn).index(line_name)
    return len(line_cn)



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

    structure = ['    "decision": "reject",']
    for ck in checks:
        structure.append(
            f'    "{ck}": {{"status": "fail", "findings": ["LLM 调用失败，未完成审核"]}},'
        )
    structure.append('    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],')
    body = "\n".join(structure)
    return f"{name} = {{\n{body}\n}}"


def sup_generate_all() -> tuple[str, str]:
    """生成全部审核模型代码与拒绝态兜底常量代码。

    返回 (models 代码, 拒绝态常量代码)。
    """
    generated = []
    reject_consts = []
    # 按任务线注册顺序输出（与 models.py 现有顺序一致，保证 diff 最小）
    for contract in sorted(find_sup_contracts(), key=_sup_line_sort_key):
        cls = contract["cls"]
        fields = _sup_classify_contract(cls)
        review_cls = _sup_review_class_name(cls)
        generated.append(
            generate_review_model(
                review_cls, _sup_cn_name(contract["path"]), fields
            )
        )
        reject_consts.append(generate_reject_constants(review_cls, fields))
    if not generated:
        _log("未发现审核模型契约", file=sys.stderr)
        return "", ""
    # 类之间空两行（PEP8 模块级类间距，与 models.py 现有格式一致）
    return "\n\n\n".join(generated), "\n\n".join(reject_consts)


# ── 写入 / 校验生成区（通用）────────────────────────────



def _sup_zone_content(raw: str, start: str, end: str) -> str | None:
    # 兼容 CRLF / LF 及历史坏行尾（\r\r\n）：边界用 \r*\n
    m = re.search(
        re.escape(start) + r"\r*\n(.*?)\r*\n" + re.escape(end),
        raw,
        re.S,
    )
    return m.group(1).strip() if m else None


def _sup_write_target(path, start: str, end: str, code: str, label: str) -> None:
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
    _log(f"已写入 {path}")



def _sup_check_target(path, start: str, end: str, code: str, label: str) -> int:
    """校验生成区与当前契约生成的代码一致；一致返回 0，否则返回 1。"""
    zone = _sup_zone_content(_read_raw(path), start, end)
    if zone is None:
        _log(f"{path.name} 中未找到 {label} 生成区标记", file=sys.stderr)
        return 1
    if _normalize_newlines(zone) == _normalize_newlines(code.strip()):
        _log(f"OK：{label}生成区与契约一致")
        return 0
    _log(f"不一致：{label}生成区与当前契约生成的代码有差异（请运行 --write 更新）", file=sys.stderr)
    return 1


# 两个生成目标：models.py 的审核模型区 + orchestrator.py 的拒绝审核常量区
def _sup_targets() -> list[tuple]:
    return [
        (CURRENT.models_path, SUP_ZONE_START, SUP_ZONE_END, "审核模型"),
        (CURRENT.orch_path, SUP_ZONE_REJECT_START, SUP_ZONE_REJECT_END, "拒绝审核常量"),
    ]


FAC_ZONE_START = "# ── 任务线装配生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
FAC_ZONE_END = "# ── 任务线装配生成区结束 ──"

# 专属节点方法生成区标记（orchestrator.py 的 _Nodes 类内）
# 语义与纯生成区不同：脚本只生成骨架（签名 + 占位注释），函数体由开发者填写；
# --write 遇已有实现跳过，--check 只验证签名存在，不比较函数体。
NODE_ZONE_START = "# ── 专属节点方法生成区：由 tools/scripts/sync_domain.py 生成骨架，函数体可改 ──"
NODE_ZONE_END = "# ── 专属节点方法生成区结束 ──"

# 任务线注册生成区标记（orchestrator.py 模块级 TASK_LINES 定义）
TL_ZONE_START = "# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
TL_ZONE_END = "# ── 任务线注册生成区结束 ──"

# Agent 挂载生成区标记（orchestrator.py 的 __init__ 内，任务线挂载）
MOUNT_ZONE_START = "# ── Agent 挂载生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
MOUNT_ZONE_END = "# ── Agent 挂载生成区结束 ──"

# 节点映射生成区标记（orchestrator.py 的 __init__ 内，_fallback_nodes）
NODEMAP_ZONE_START = "# ── 节点映射生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
NODEMAP_ZONE_END = "# ── 节点映射生成区结束 ──"

# 渲染上下文生成区标记（orchestrator.py 的 _Nodes 类内，完整生成勿手改）
CTX_ZONE_START = "# ── 渲染上下文生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
CTX_ZONE_END = "# ── 渲染上下文生成区结束 ──"

# FallbackRules import 生成区标记（orchestrator.py 顶部 import 区，整体生成勿手改）
IMPORT_ZONE_START = "# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
IMPORT_ZONE_END = "# ── FallbackRules import 生成区结束 ──"

# Report import 生成区标记（orchestrator.py 顶部 import 区，整体生成勿手改）
REPORT_IMPORT_ZONE_START = "# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
REPORT_IMPORT_ZONE_END = "# ── Report import 生成区结束 ──"

# 任务线 import 生成区标记（orchestrator.py 顶部，from .tasks.{线} import 三件套）
LINE_IMPORT_ZONE_START = "# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
LINE_IMPORT_ZONE_END = "# ── 任务线 import 生成区结束 ──"

# Report 校验生成区标记（models.py，手写 Report 区之前；validate 由脚本按手写字段生成）
REPORT_VALIDATION_ZONE_START = "# ── Report 校验生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
REPORT_VALIDATION_ZONE_END = "# ── Report 校验生成区结束 ──"

# Report 基类 import 生成区标记（reports.py 顶部：ModelMixin + 各线 Validation）
REPORT_BASE_IMPORT_ZONE_START = "# ── Report 基类 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
REPORT_BASE_IMPORT_ZONE_END = "# ── Report 基类 import 生成区结束 ──"

# Report 组装器生成区标记（orchestrator.py 的 __init__ 内，整体生成勿手改）
REPORT_ZONE_START = "# ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
REPORT_ZONE_END = "# ── Report 组装器生成区结束 ──"

# FallbackRules 注册生成区标记（orchestrator.py 的 __init__ 内，整体生成勿手改）
FALLBACK_RULES_ZONE_START = "# ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──"
FALLBACK_RULES_ZONE_END = "# ── FallbackRules 注册生成区结束 ──"

# 生成区正则：允许标记前有缩进（生成区嵌在 create() 函数体内，行首带空格）
_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(FAC_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(FAC_ZONE_END)
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

# 任务线 import 生成区正则（orchestrator.py 顶部，from .tasks.{线} import 三件套）
_LINE_IMPORT_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(LINE_IMPORT_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(LINE_IMPORT_ZONE_END)
)

# Report 校验生成区正则（models.py，mixin 类块）
_REPORT_VALIDATION_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(REPORT_VALIDATION_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(REPORT_VALIDATION_ZONE_END)
)


# ── Report 校验生成（手写 Report 字段 → 自动生成 validate mixin）──────────

def _report_field_kind(annot: ast.AST) -> str:
    """ast 类型注解 → 校验 kind（str/str_null/int/str_list/obj_list/dict）。"""
    if isinstance(annot, ast.Name):
        return {"str": "str", "int": "int", "dict": "dict", "list": "list"}.get(
            annot.id, "str"
        )
    if isinstance(annot, ast.BinOp) and isinstance(annot.op, ast.BitOr):
        # str | None → str_null（可空标量）
        left = _report_field_kind(annot.left)
        return left if left.endswith("_null") else f"{left}_null"
    if isinstance(annot, ast.Subscript) and isinstance(annot.value, ast.Name):
        base = annot.value.id
        if base == "list":
            inner = annot.slice
            if (
                isinstance(inner, ast.Subscript)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "dict"
            ):
                return "obj_list"          # list[dict[str, Any]] → 结构化列表
            if isinstance(inner, ast.Name) and inner.id == "str":
                return "str_list"          # list[str]
            return "list"
        if base == "dict":
            return "dict"
    return "str"


def _field_metadata(call_node: ast.Call) -> dict:
    """提取 field(metadata={...}) 里的 metadata 键值（source/required/item_validator）。"""
    md: dict = {}
    for kw in call_node.keywords:
        if kw.arg == "metadata" and isinstance(kw.value, ast.Dict):
            for k, v in zip(kw.value.keys, kw.value.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                    md[k.value] = v.value
    return md


# Report 基类 import 生成区正则（reports.py 顶部）
_REPORT_BASE_IMPORT_ZONE_PATTERN = (
    r"[ \t]*"
    + re.escape(REPORT_BASE_IMPORT_ZONE_START)
    + r"\r*\n(.*?)\r*\n[ \t]*"
    + re.escape(REPORT_BASE_IMPORT_ZONE_END)
)


def generate_report_base_imports_code(lines: list[str]) -> str:
    """生成 reports.py 顶部的 Report 基类 import（ModelMixin + 各线 Validation）。

    只包含 reports.py 里**已定义** Report 类的线（未定义则跳过，避免 NameError）。
    """
    names = ["ModelMixin"]
    for line in lines:
        # 所有已注册线都引入 Validation（register 阶段生成占位，类写后重写为真实）
        names.append(f"{_report_class(line)}Validation")
    return (
        "from .models import (\n"
        + "".join(f"    {n},\n" for n in names)
        + ")\n"
    )


def write_report_base_imports(path: Path, lines: list[str]) -> None:
    """整体重写 reports.py 的 Report 基类 import 生成区（缺失时先创建骨架）。"""
    if not path.exists():
        path.write_text(
            '"""会议域全部任务线的最终输出 Report 类 —— 手写区。"""\n'
            "from __future__ import annotations\n"
            "\n"
            "from dataclasses import dataclass, field\n"
            "\n"
            f"{REPORT_BASE_IMPORT_ZONE_START}\n"
            f"{REPORT_BASE_IMPORT_ZONE_END}\n"
            "\n"
        )
        _log(f"已创建 {path.name}（骨架，请追加 Report 类）")
        return
    raw = _read_raw(path)
    if (
        REPORT_BASE_IMPORT_ZONE_START not in raw
        or REPORT_BASE_IMPORT_ZONE_END not in raw
    ):
        sys.exit(
            f"{path.name} 中未找到 Report 基类 import 生成区标记。请先手动添加：\n"
            f"{REPORT_BASE_IMPORT_ZONE_START}\n"
            f"from .models import (ModelMixin, 各线 Validation)\n"
            f"{REPORT_BASE_IMPORT_ZONE_END}"
        )
    m = re.search(_REPORT_BASE_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 Report 基类 import 生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = generate_report_base_imports_code(lines)
    block = (
        f"{REPORT_BASE_IMPORT_ZONE_START}"
        + nl
        + (nl + code + nl if code else nl)
        + f"{REPORT_BASE_IMPORT_ZONE_END}"
    )
    new_raw = re.sub(
        _REPORT_BASE_IMPORT_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    _log(f"已写入 {path.name} Report 基类 import 生成区")


def check_report_base_imports(path: Path, lines: list[str]) -> int:
    """校验 reports.py 的 Report 基类 import 生成区与已定义 Report 一致。"""
    raw = _read_raw(path)
    m = re.search(_REPORT_BASE_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 Report 基类 import 生成区标记", file=sys.stderr)
        return 1
    expected = generate_report_base_imports_code(lines)
    if m.group(1).strip() != expected.strip():
        _log(f"不一致：{path.name} Report 基类 import 生成区与已定义 Report 类有差异（请运行 --write 更新）", file=sys.stderr)
        return 1
    _log(f"OK：Report 基类 import 生成区一致（{len(lines)} 条线）")
    return 0


def _parse_report_fields(report_cls: str) -> list[dict]:
    """ast 解析手写 Report 类的字段声明。

    返回 [{name, kind, source, item_validator}]：
    - kind：由类型注解推导（str/str_null/str_list/obj_list/dict）
    - item_validator：``field(metadata={"item_validator": "action"})``（obj_list 逐条校验器名）
    """
    tree = ast.parse(_read_py(CURRENT.reports_path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == report_cls:
            out = []
            for stmt in node.body:
                if not (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                ):
                    continue
                info = {
                    "name": stmt.target.id,
                    "kind": _report_field_kind(stmt.annotation),
                    "source": None,
                    "item_validator": None,
                }
                if (
                    isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Name)
                    and stmt.value.func.id == "field"
                ):
                    md = _field_metadata(stmt.value)
                    info["source"] = md.get("source")
                    if "item_validator" in md:
                        info["item_validator"] = md["item_validator"]
                out.append(info)
            return out
    return []


def _report_validation_lines(f: dict) -> str:
    """单字段的校验代码行（8 空格缩进起，可多行）。

    缺失字段一律回退默认值（不报错）；仅做多余字段（白名单）与类型检查。
    """
    n = f["name"]
    if f["kind"] == "obj_list":
        lines = [
            f'        if not isinstance(data.get("{n}") or [], list):',
            f'            raise OutputValidationError("{n} 必须是数组")',
        ]
        iv = f.get("item_validator")
        if iv:
            lines.append(f'        for index, item in enumerate(data.get("{n}") or []):')
            lines.append(f'            _{iv}(item, f"{n}[{{index}}]")')
        return "\n".join(lines)
    if f["kind"] == "str_list":
        return f'        _string_list(data.get("{n}") or [], "{n}")'
    if f["kind"] == "dict":
        return (
            f'        if data.get("{n}") is not None and not isinstance(data["{n}"], dict):\n'
            f'            raise OutputValidationError("{n} 必须是对象")'
        )
    if f["kind"] == "int":
        return (
            f'        if data.get("{n}") is not None and not isinstance(data["{n}"], int):\n'
            f'            raise OutputValidationError("{n} 必须是整数")'
        )
    if f["kind"].endswith("_null"):
        return (
            f'        if data.get("{n}") is not None:\n'
            f'            _string(data["{n}"], "{n}")'
        )
    # str：缺失/None/空 → 空串通过（必填由组装器保证，不做缺失报错）
    return f'        _string(data.get("{n}") or "", "{n}")'


def _report_default_expr(f: dict) -> str:
    """return cls(...) 里字段的取值表达式（缺失回退默认）。"""
    n = f["name"]
    if f["kind"] == "str":
        return f'data.get("{n}") or ""'
    if f["kind"] in ("obj_list", "str_list"):
        return f'data.get("{n}") or []'
    return f'data.get("{n}")'


def generate_report_validation_code(lines: list[str]) -> str:
    """生成全部已定义 Report 类的校验 mixin（写入 models.py Report 校验生成区）。

    未定义 Report 类的线（如新线尚未手写）跳过——与 Report import 生成区同一检测。
    """
    blocks = []
    for line in lines:
        report_cls = _report_class(line)
        fields_info = _parse_report_fields(report_cls)
        if not fields_info:
            # 占位：Report 类尚未手写（register 阶段）——先放空类，
            # 类一旦定义（写字段）后 sync_domain 全量会按字段重写为真实校验。
            blocks.append(
                f"class {report_cls}Validation:\n"
                f"    pass\n"
            )
            continue
        allowed = ", ".join(f'"{f["name"]}"' for f in fields_info)
        assign_lines = [
            f'            {f["name"]}={_report_default_expr(f)},'
            for f in fields_info
        ]
        val_lines = "\n".join(_report_validation_lines(f) for f in fields_info)
        blocks.append(
            f"class {report_cls}Validation:\n"
            f'    """{report_cls} 的校验逻辑（由脚本按手写字段自动生成）。"""\n'
            f"\n"
            f"    @classmethod\n"
            f'    def validate(cls, data: dict) -> "{report_cls}":\n'
            f"        allowed = {{{allowed}}}\n"
            f"\n"
            f"        if not isinstance(data, dict):\n"
            f'            raise OutputValidationError("{report_cls} 必须是 JSON 对象")\n'
            f"\n"
            f"        extra = set(data) - allowed\n"
            f"        if extra:\n"
            f"            raise OutputValidationError(\n"
            f'                f"{report_cls} 字段不一致：多余={{sorted(extra)}}"\n'
            f"            )\n"
            f"\n"
            f"{val_lines}\n"
            f"\n"
            f"        return cls(\n"
            + "\n".join(assign_lines)
            + f"\n        )\n"
        )
    return "\n\n".join(blocks)


def write_report_validation(path: Path, lines: list[str]) -> None:
    """整体重写 models.py 的 Report 校验生成区。"""
    raw = _read_raw(path)
    if (
        REPORT_VALIDATION_ZONE_START not in raw
        or REPORT_VALIDATION_ZONE_END not in raw
    ):
        sys.exit(
            f"{path.name} 中未找到 Report 校验生成区标记。请先手动添加：\n"
            f"{REPORT_VALIDATION_ZONE_START}\n（现有手写 Report 的 validate 删除，"
            f"类继承 XxxReportValidation 由脚本生成）\n"
            f"{REPORT_VALIDATION_ZONE_END}"
        )
    m = re.search(_REPORT_VALIDATION_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 Report 校验生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = generate_report_validation_code(lines)
    block = (
        f"{REPORT_VALIDATION_ZONE_START}"
        + nl
        + (nl + code + nl if code else nl)
        + f"{REPORT_VALIDATION_ZONE_END}"
    )
    new_raw = re.sub(
        _REPORT_VALIDATION_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    _log(f"已写入 {path.name} Report 校验生成区")


def check_report_validation(path: Path, lines: list[str]) -> int:
    """校验 Report 校验生成区与手写 Report 字段一致。"""
    raw = _read_raw(path)
    m = re.search(_REPORT_VALIDATION_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 Report 校验生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_report_validation_code(lines)
    if _normalize_newlines(zone) != _normalize_newlines(expected):
        _log(
            f"不一致：Report 校验生成区与手写 Report 字段有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：Report 校验生成区一致（{len(lines)} 条线）")
    return 0


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
    tasks_dir = tasks_dir or CURRENT.tasks_dir
    return sorted(
        d.name
        for d in tasks_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )


def line_class_name(line: str, suffix: str) -> str:
    """线名 + 后缀 → 类名。例：minutes_generation + Agent → MinutesGenerationAgent。"""
    prefix = "".join(part.capitalize() for part in line.split("_"))
    return f"{prefix}{suffix}"


# ── 代码生成 ─────────────────────────────────────────────────

def generate_lines_code(lines: list[str]) -> str:
    """生成装配代码：每条线 3 行（agent / supervisor / render）。

    键名统一为 ``{line}_agent`` / ``{line}_supervisor`` / ``{line}_render``，
    与 __init__ 挂载的属性名、TASK_LINES 的 agent_attr 完全一致
    （一个名字贯穿工厂→挂载→注册表→getattr）。

    行首不带缩进（写入时由 _fac_write_target 统一加 create() 函数体缩进）。
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
    tasks_dir = tasks_dir or CURRENT.tasks_dir
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
            f"    async def {fn}(self, state: {CURRENT.state_class()}) -> dict:\n"
            f"        text, structure = _fallback_text(\n"
            f'            state, "{line}", {base}_FALLBACK_RULES)\n'
            f'        line_dict = {{"rendered": text, "degraded": True}}\n'
            f"        if structure is not None:\n"
            f'            line_dict["structure"] = structure\n'
            f'        return {{\"lines\": {{\"{line}\": line_dict}}, '
            f'"quality_degraded": True}}\n'
        )
    return (
        f"    async def {fn}(self, state: {CURRENT.state_class()}) -> dict:\n"
        f"        ## 这里新增你的代码：降级输出（写入 "
        f'lines["{line}"]["rendered"] + degraded）\n'
        f"        ## 未实现时返回空降级兜底（保证可运行）；实现后请替换下方 return\n"
        f'        return {{"lines": {{"{line}": {{"rendered": "（降级）", '
        f'"degraded": True}}}}, "quality_degraded": True}}\n'
    )



def _contract_base(line: str, tasks_dir: Path | None = None) -> str:
    """线名 → 契约基名：从该线 contracts.py 的契约类名推导。

    例：minutes_generation/contracts.py 里 MinutesGenerationContract
    → 类名去 GenerationContract 后缀 "Minutes" → 全大写 "MINUTES"
    （用于推导 _EMPTY_MINUTES / _REJECT_MINUTES_REVIEW）。
    """
    tasks_dir = tasks_dir or CURRENT.tasks_dir
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


def _task_model_class(line: str) -> str:
    """线名 → 生成模型类名（MinutesGenerationContract → Minutes）。"""
    contracts_path = CURRENT.tasks_dir / line / "contracts.py"
    if contracts_path.exists():
        text = contracts_path.read_text(encoding="utf-8")
        for cls_name in re.findall(r"class\s+(\w+GenerationContract)\b", text):
            return cls_name.removesuffix("GenerationContract")
    return _pascal(_contract_base(line))


def _task_readiness_issues(line: str) -> list[str]:
    """Return actionable issues that block runtime wiring for one task line."""
    issues: list[str] = []
    task_dir = CURRENT.tasks_dir / line
    contracts_path = task_dir / "contracts.py"
    prompts_path = task_dir / "prompts.py"
    report_cls = ""
    upper = _contract_base(line) if contracts_path.exists() else line.upper()
    cls = line_class_name(line, "")

    if not contracts_path.exists():
        issues.append(f"缺少 {contracts_path.relative_to(ROOT)}")
    else:
        text = contracts_path.read_text(encoding="utf-8-sig")
        if not re.search(r"class\s+\w+GenerationContract\b", text):
            issues.append(
                f"{contracts_path.relative_to(ROOT)} 还没有 *GenerationContract"
            )
        else:
            report_cls = _report_class(line)
        if not re.search(r"class\s+\w+SupervisorContract\b", text):
            issues.append(
                f"{contracts_path.relative_to(ROOT)} 还没有 *SupervisorContract"
            )
        if f"{upper}_GENERATION_OUTPUT_CONTRACT" not in text:
            issues.append(
                f"{contracts_path.relative_to(ROOT)} 还没有 "
                f"{upper}_GENERATION_OUTPUT_CONTRACT"
            )
        if f"{upper}_SUPERVISOR_OUTPUT_CONTRACT" not in text:
            issues.append(
                f"{contracts_path.relative_to(ROOT)} 还没有 "
                f"{upper}_SUPERVISOR_OUTPUT_CONTRACT"
            )

    if not prompts_path.exists():
        issues.append(f"缺少 {prompts_path.relative_to(ROOT)}")
    else:
        text = prompts_path.read_text(encoding="utf-8-sig")
        for name in (
            f"{upper}_GENERATION_SYSTEM_PROMPT",
            f"{upper}_SUPERVISOR_DOMAIN_PROMPT",
            f"{upper}_RENDER_PROMPT",
            f"{upper}_RENDER_TEMPLATE_PROMPT",
        ):
            if name not in text:
                issues.append(f"{prompts_path.relative_to(ROOT)} 还没有 {name}")

    step_specs = {
        f"{line}_agent.py": (f"class {cls}Agent", "async def run"),
        f"{line}_supervisor.py": (f"class {cls}Supervisor", "async def review"),
        f"{line}_render.py": (f"class {cls}Render", "async def run", "async def stream"),
    }
    for fname, needles in step_specs.items():
        path = task_dir / "steps" / fname
        if not path.exists():
            issues.append(f"缺少 {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8-sig")
        missing = [needle for needle in needles if needle not in text]
        if missing:
            issues.append(
                f"{path.relative_to(ROOT)} 还没有必要结构：{', '.join(missing)}"
            )

    if report_cls and not _has_report_class(line):
        issues.append(
            f"{CURRENT.reports_path.relative_to(ROOT)} 还没有 class {report_cls}"
        )

    return issues


def _runtime_readiness_issues(lines: list[str]) -> list[str]:
    issues: list[str] = []
    for line in lines:
        issues.extend(_task_readiness_issues(line))
    return issues


def _print_readiness_issues(issues: list[str]) -> None:
    if not issues:
        return
    print("需要先补齐任务线业务代码：", file=sys.stderr)
    for issue in issues:
        print(f"  - {issue}", file=sys.stderr)
    print("", file=sys.stderr)
    print("提示：sync_domain 已经先同步 models.py 中的模型/审核模型。", file=sys.stderr)
    print("下一步：补齐上面的文件后重新运行：", file=sys.stderr)
    print(f"  python tools/scripts/sync_domain.py --domain {CURRENT.name}", file=sys.stderr)


def generate_task_agent_code(line: str) -> str:
    """生成 {line}_agent.py（骨架；文件已存在则保留用户实现，不覆盖）。"""
    upper, cls, model, cn = (
        line.upper(),
        line_class_name(line, "Agent"),
        _task_model_class(line),
        CURRENT.line_cn_names().get(line, line),
    )
    return (
        "from __future__ import annotations\n"
        "\n"
        "from llm_client import LLMClient\n"
        f"from ....models import {model}\n"
        f"from ..prompts import (\n"
        f"    {upper}_GENERATION_SYSTEM_PROMPT,\n"
        ")\n"
        f"from ..contracts import {upper}_GENERATION_OUTPUT_CONTRACT\n"
        "\n"
        "\n"
        f"class {cls}:\n"
        f'    """基于会议理解和视角模型生成{cn}草稿（个人视角或客观全员视角）。"""\n'
        "\n"
        "    def __init__(self, client: LLMClient) -> None:\n"
        "        self.client = client\n"
        "\n"
        f"    async def run(self, shared_context: str) -> {model}:\n"
        "        return await self.client.structured(\n"
        f"            {upper}_GENERATION_SYSTEM_PROMPT,\n"
        "            shared_context,\n"
        f"            {model},\n"
        f"            {upper}_GENERATION_OUTPUT_CONTRACT,\n"
        "        )\n"
    )


def generate_task_supervisor_code(line: str) -> str:
    """生成 {line}_supervisor.py（骨架；文件已存在则保留用户实现，不覆盖）。"""
    upper, cls, model, cn = (
        line.upper(),
        line_class_name(line, "Supervisor"),
        _task_model_class(line),
        CURRENT.line_cn_names().get(line, line),
    )
    return (
        "from __future__ import annotations\n"
        "\n"
        "from supervisor import GlobalSupervisor\n"
        "\n"
        "from llm_client import LLMClient\n"
        f"from ....models import {model}SupervisorReview\n"
        f"from ..prompts import (\n"
        f"    {upper}_SUPERVISOR_DOMAIN_PROMPT,\n"
        ")\n"
        f"from ..contracts import {upper}_SUPERVISOR_OUTPUT_CONTRACT\n"
        "\n"
        "\n"
        f"class {cls}:\n"
        f'    """{cn}任务的领域监督者。\n'
        "\n"
        f"    prompt = 全局整体标准（注入） + {cn}领域审核规则，\n"
        "    一次 LLM 调用完成双重评判，决定 approve / revise / reject。\n"
        '    """\n'
        "\n"
        "    def __init__(self, client: LLMClient) -> None:\n"
        "        self.client = client\n"
        "        self._system_prompt = GlobalSupervisor.build_prompt(\n"
        f"            {upper}_SUPERVISOR_DOMAIN_PROMPT\n"
        "        )\n"
        "\n"
        f"    async def review(self, context: str) -> {model}SupervisorReview:\n"
        "        return await self.client.structured(\n"
        "            self._system_prompt,\n"
        "            context,\n"
        f"            {model}SupervisorReview,\n"
        f"            {upper}_SUPERVISOR_OUTPUT_CONTRACT,\n"
        "        )\n"
    )


def generate_task_render_code(line: str) -> str:
    """生成 {line}_render.py（基础骨架；需要额外方法（如 extract_actions）在生成后手加）。"""
    upper, cls, cn = (
        line.upper(),
        line_class_name(line, "Render"),
        CURRENT.line_cn_names().get(line, line),
    )
    return (
        "from __future__ import annotations\n"
        "\n"
        "from collections.abc import AsyncIterator\n"
        "\n"
        "from tools.prompt_utils import build_render_prompt\n"
        "\n"
        "from llm_client import LLMClient\n"
        f"from ..prompts import {upper}_RENDER_PROMPT, {upper}_RENDER_TEMPLATE_PROMPT\n"
        "\n"
        "\n"
        f"class {cls}:\n"
        f'    """把已批准的{cn}草稿渲染为最终输出（支持模板与流式）。"""\n'
        "\n"
        "    def __init__(self, client: LLMClient) -> None:\n"
        "        self.client = client\n"
        "\n"
        "    @staticmethod\n"
        "    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:\n"
        '        """组装渲染 prompt 与用户消息（普通与流式共用）。"""\n'
        "        return build_render_prompt(\n"
        "            context,\n"
        "            template,\n"
        f"            {upper}_RENDER_PROMPT,\n"
        f"            {upper}_RENDER_TEMPLATE_PROMPT,\n"
        "        )\n"
        "\n"
        '    async def run(self, approved_context: str, template: str = "") -> str:\n'
        "        prompt, user = self._prompt_and_user(approved_context, template)\n"
        "        return await self.client.text(prompt, user)\n"
        "\n"
        '    async def stream(self, approved_context: str, template: str = "") -> AsyncIterator[str]:\n'
        "        prompt, user = self._prompt_and_user(approved_context, template)\n"
        "        async for chunk in self.client.stream_text(prompt, user):\n"
        "            yield chunk\n"
    )


def generate_task_init_code(line: str) -> str:
    """生成 tasks/{line}/__init__.py（纯导出模板，整体重写）。"""
    cls_agent, cls_render, cls_sup, cn = (
        line_class_name(line, "Agent"),
        line_class_name(line, "Render"),
        line_class_name(line, "Supervisor"),
        CURRENT.line_cn_names().get(line, line),
    )
    return (
        f'"""{line} —— {cn}任务组。\n'
        "\n"
        f"流水线：agent（生成{cn}草稿）→ supervisor（领域审核 + 全局标准）→ render（渲染正文）。\n"
        '"""\n'
        "\n"
        f"from .steps.{line}_agent import {cls_agent}\n"
        f"from .steps.{line}_render import {cls_render}\n"
        f"from .steps.{line}_supervisor import {cls_sup}\n"
        "\n"
        "__all__ = [\n"
        f'    "{cls_agent}",\n'
        f'    "{cls_render}",\n'
        f'    "{cls_sup}",\n'
        "]\n"
    )


def write_task_skels(lines: list[str]) -> None:
    """为每条线创建缺失的任务线四件套（steps/ 三件 + 任务线 __init__.py）。

    - ``steps/`` 下 agent/supervisor/render：文件已存在则保留（可能含用户手写的
      额外方法），只创建缺失文件；``steps/__init__.py`` 缺失时创建包标记。
    - 任务线 ``__init__.py``：纯导出模板，**始终整体重写**——PyCharm 新建包会
      生成空 ``__init__.py``，必须填充导出，否则 ``from .tasks.xxx import`` 失败。
    """
    for line in lines:
        d = CURRENT.tasks_dir / line
        d.mkdir(parents=True, exist_ok=True)
        steps = d / "steps"
        steps.mkdir(parents=True, exist_ok=True)
        steps_init = steps / "__init__.py"
        if not steps_init.exists():
            steps_init.write_text(
                f'"""{line} 流水线步骤：agent（生成草稿）→ supervisor（审核）→ render（渲染）。"""\n',
                encoding="utf-8",
            )
            _log(f"已创建 {steps_init.relative_to(CURRENT.dir)}")
        for fname, gen in (
            (f"{line}_agent.py", generate_task_agent_code),
            (f"{line}_supervisor.py", generate_task_supervisor_code),
            (f"{line}_render.py", generate_task_render_code),
            ("__init__.py", generate_task_init_code),
        ):
            path = (steps if fname != "__init__.py" else d) / fname
            if fname == "__init__.py":
                path.write_text(gen(line), encoding="utf-8")
                _log(f"已更新 {path.relative_to(CURRENT.dir)}")
            elif path.exists():
                continue
            else:
                path.write_text(gen(line), encoding="utf-8")
                _log(f"已创建 {path.relative_to(CURRENT.dir)}")


def check_task_skels(lines: list[str]) -> int:
    """校验任务线四件套：文件存在 + 必要类/方法齐全（函数体可改，内容不校验）。"""
    rc = 0
    for line in lines:
        d = CURRENT.tasks_dir / line
        steps = d / "steps"
        cls = line_class_name(line, "")
        required = {
            f"{line}_agent.py": (
                f"class {cls}Agent",
                "async def run",
            ),
            f"{line}_supervisor.py": (
                f"class {cls}Supervisor",
                "async def review",
            ),
            f"{line}_render.py": (
                f"class {cls}Render",
                "async def run",
                "async def stream",
            ),
            "__init__.py": (f"{cls}Agent", f"{cls}Render", f"{cls}Supervisor"),
        }
        for fname, needles in required.items():
            path = (steps if fname != "__init__.py" else d) / fname
            if not path.exists():
                _log(f"缺失：{path.relative_to(CURRENT.dir)}（请运行 --write 生成骨架）", file=sys.stderr)
                rc = 1
                continue
            text = path.read_text(encoding="utf-8")
            missing = [n for n in needles if n not in text]
            if missing:
                _log(f"{path.relative_to(CURRENT.dir)} 缺少必要结构：{missing}", file=sys.stderr)
                rc = 1
    if not rc:
        _log(f"OK：任务线骨架齐全（{len(lines)} 条线 × 四件套）")
    return rc


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

    所有线的 render_context 完全同构：视角模式 / objective_perspective /
    state 上下文行（领域配置 RENDER_CONTEXT_STATE_LINES）/
    已批准{中文名}草稿 / {中文名}审核结论。中文名查领域 domain_config。
    """
    blocks = []
    for line in lines:
        cn = CURRENT.line_cn_names().get(line, line)
        state_lines = CURRENT.render_context_state_lines()
        blocks.append(
            f"    def _{line}_render_context(self, state: {CURRENT.state_class()}) -> str:\n"
            f"        mode = self._mode_label(state)\n"
            f'        line = _line(state, "{line}")\n'
            f'        review = line.get("review") or {{}}\n'
            f"        return (\n"
            f'            f"视角模式：{{mode}}\\n"\n'
            f'            f"objective_perspective：'
            f"{{bool(state.get('objective_perspective'))}}\\n\\n\"\n"
            + "\n".join(state_lines)
            + "\n"
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
    _log(f"已写入 {path.name} 渲染上下文生成区")


def check_render_context(path: Path, lines: list[str]) -> int:
    """校验渲染上下文生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_CTX_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到渲染上下文生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_render_context_code(lines)
    if _normalize_newlines(zone).strip() != _normalize_newlines(expected).strip():
        _log(
            f"不一致：渲染上下文生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：渲染上下文生成区一致（{len(lines)} 条线）")
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
    _log(f"已写入 {path.name} FallbackRules import 生成区")


def check_fallback_imports(path: Path, lines: list[str]) -> int:
    """校验 FallbackRules import 生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 FallbackRules import 生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_fallback_import_code(lines)
    if _normalize_newlines(zone).strip() != _normalize_newlines(expected).strip():
        _log(
            f"不一致：FallbackRules import 生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：FallbackRules import 生成区一致（{len(lines)} 条线）")
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
    """reports.py 是否已定义该线的 Report 类（未定义则不生成引用，避免 NameError）。"""
    return bool(
        re.search(
            rf"class\s+{re.escape(_report_class(line))}\b",
            CURRENT.reports_path.read_text(encoding="utf-8"),
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
    return f"from .reports import (\n    " + ",\n    ".join(names) + ",\n)"


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


def generate_line_imports_code(lines: list[str]) -> str:
    """生成 orchestrator.py 顶部的任务线 import（from .tasks.{线} import 三件套）。"""
    blocks = []
    for line in lines:
        base = _pascal(line)
        blocks.append(
            f"from .tasks.{line} import (\n"
            f"    {base}Agent,\n"
            f"    {base}Render,\n"
            f"    {base}Supervisor,\n"
            f")\n"
        )
    return "\n".join(blocks)


def write_line_imports(path: Path, lines: list[str]) -> None:
    """整体重写 orchestrator.py 的任务线 import 生成区。"""
    raw = _read_raw(path)
    if LINE_IMPORT_ZONE_START not in raw or LINE_IMPORT_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到 任务线 import 生成区标记。请先手动添加：\n"
            f"{LINE_IMPORT_ZONE_START}\n（现有手写任务线 import 移入此处）\n"
            f"{LINE_IMPORT_ZONE_END}"
        )
    m = re.search(_LINE_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        sys.exit(f"{path.name} 中 任务线 import 生成区标记不完整")
    nl = "\r\n" if "\r\n" in raw else "\n"
    code = generate_line_imports_code(lines)
    block = (
        f"{LINE_IMPORT_ZONE_START}"
        + nl
        + (nl + code + nl if code else nl)
        + f"{LINE_IMPORT_ZONE_END}"
    )
    new_raw = re.sub(
        _LINE_IMPORT_ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    _log(f"已写入 {path.name} 任务线 import 生成区")


def write_factory_line_imports(lines: list[str]) -> None:
    """写当前 domain factory.py 的任务线 import 生成区（与 orchestrator 同模板）。

    供 register_task.py（新增线第一步）与 _run_write_factory 共用。
    """
    write_line_imports(CURRENT.factory_path, lines)


def check_line_imports(path: Path, lines: list[str]) -> int:
    """校验任务线 import 生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_LINE_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 任务线 import 生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_line_imports_code(lines)
    if zone.strip() != expected.strip():
        _log(
            f"不一致：任务线 import 生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：任务线 import 生成区一致（{len(lines)} 条线）")
    return 0


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
    _log(f"已写入 {path.name} Report import 生成区")


def check_report_imports(path: Path, lines: list[str]) -> int:
    """校验 Report import 生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_REPORT_IMPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 Report import 生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_report_import_code(lines)
    if zone.strip() != expected.strip():
        _log(
            f"不一致：Report import 生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：Report import 生成区一致（{len(lines)} 条线）")
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
    _log(f"已写入 {path.name} Report 组装器生成区")


def check_report_assemblers(path: Path, lines: list[str]) -> int:
    """校验 Report 组装器生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_REPORT_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 Report 组装器生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_report_assembler_code(lines)
    if _normalize_newlines(zone).strip() != _normalize_newlines(expected).strip():
        _log(
            f"不一致：Report 组装器生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：Report 组装器生成区一致（{len(lines)} 条线）")
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
    _log(f"已写入 {path.name} FallbackRules 注册生成区")


def check_fallback_rules(path: Path, lines: list[str]) -> int:
    """校验 FallbackRules 注册生成区与当前目录生成一致。"""
    raw = _read_raw(path)
    m = re.search(_FALLBACK_RULES_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 FallbackRules 注册生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    expected = generate_fallback_rules_code(lines)
    if _normalize_newlines(zone).strip() != _normalize_newlines(expected).strip():
        _log(
            f"不一致：FallbackRules 注册生成区与当前目录生成的代码有差异"
            f"（请运行 --write 更新）",
            file=sys.stderr,
        )
        return 1
    _log(f"OK：FallbackRules 注册生成区一致（{len(lines)} 条线）")
    return 0


# ── 写入 / 校验（复用 sync_domain.py 的生成区模式）──


def _fac_write_target(path: Path, code: str) -> None:
    """把生成的装配代码写入指定文件的生成区（无标记则报错提示）。"""
    raw = _read_raw(path)
    if FAC_ZONE_START not in raw or FAC_ZONE_END not in raw:
        sys.exit(
            f"{path.name} 中未找到任务线装配生成区标记。请先手动添加：\n"
            f"{FAC_ZONE_START}\n（现有任务线装配代码移入此处）\n{FAC_ZONE_END}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    # 生成区内容缩进与 create() 函数体一致（12 空格），行尾与文件一致
    indented = nl.join(
        f"            {ln}" for ln in code.split("\n")
    )
    block = (
        f"            {FAC_ZONE_START}"
        + nl
        + nl
        + indented
        + nl
        + nl
        + f"            {FAC_ZONE_END}"
    )
    new_raw = re.sub(
        _ZONE_PATTERN,
        lambda _m: block,
        raw,
        flags=re.S,
    )
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)
    _log(f"已写入 {path}")



def _fac_check_target(path: Path, code: str) -> int:
    """校验生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到任务线装配生成区标记", file=sys.stderr)
        return 1
    zone_lines = [
        ln.strip() for ln in m.group(1).splitlines() if ln.strip()
    ]
    zone = "\n".join(zone_lines)
    if zone == _normalize_newlines(code.strip()):
        _log(f"OK：任务线装配生成区与目录一致（{path.name}）")
        return 0
    _log(
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
        _log(f"无新增骨架：{path.name} 全部任务线已有降级节点方法")
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
    _log(f"已追加 {len(additions)} 个降级节点方法骨架到 {path}")


def check_nodes(path: Path, lines: list[str]) -> int:
    """校验每条线的 render/fallback 骨架签名都存在（不比较函数体）。"""
    raw = _read_raw(path)
    m = re.search(_NODE_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到专属节点方法生成区标记", file=sys.stderr)
        return 1
    zone = m.group(1)
    missing = []
    for line in lines:
        fn = f"_{line}_fallback_node"
        if f"async def {fn}" not in zone:
            missing.append(fn)
    if missing:
        _log(f"缺失降级节点方法骨架: {missing}", file=sys.stderr)
        return 1
    _log(f"OK：降级节点方法签名齐全（{len(lines)} 条线 × fallback）")
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
    _log(f"已写入 {path} 任务线注册生成区")


def check_task_lines(path: Path, lines: list[str]) -> int:
    """校验任务线注册生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_TL_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到任务线注册生成区标记", file=sys.stderr)
        return 1
    # 保留行内缩进：只 strip 首尾空白，逐行比较前统一换行
    zone = _normalize_newlines(m.group(1)).strip()
    expected = _normalize_newlines(generate_task_lines_code(lines)).strip()
    if zone == expected:
        _log(f"OK：任务线注册生成区与目录一致（{path.name}）")
        return 0
    _log(
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
    _log(f"已写入 {path} Agent 挂载生成区")


def check_mount(path: Path, lines: list[str]) -> int:
    """校验 Agent 挂载生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_MOUNT_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到 Agent 挂载生成区标记", file=sys.stderr)
        return 1
    zone = _normalize_newlines(m.group(1)).strip()
    expected = _normalize_newlines(generate_mount_code(lines)).strip()
    if zone == expected:
        _log(f"OK：Agent 挂载生成区与目录一致（{path.name}）")
        return 0
    _log(
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
    _log(f"已写入 {path} 节点映射生成区")


def check_node_map(path: Path, lines: list[str]) -> int:
    """校验节点映射生成区与目录一致；一致返回 0，否则返回 1。"""
    raw = _read_raw(path)
    m = re.search(_NODEMAP_ZONE_PATTERN, raw, re.S)
    if m is None:
        _log(f"{path.name} 中未找到节点映射生成区标记", file=sys.stderr)
        return 1
    zone = _normalize_newlines(m.group(1)).strip()
    expected = _normalize_newlines(generate_node_map_code(lines)).strip()
    if zone == expected:
        _log(f"OK：节点映射生成区与目录一致（{path.name}）")
        return 0
    _log(
        f"不一致：节点映射生成区与当前目录生成的代码有差异（请运行 --write 更新）",
        file=sys.stderr,
    )
    return 1




# ── 领域 core understanding 自动接线 ─────────────────────────

def _core_understanding_info() -> dict | None:
    """发现约定式领域理解 Agent。"""
    core_dir = CURRENT.dir / f"{CURRENT.name}_core"
    agent_path = core_dir / f"{CURRENT.name}_understanding_agent.py"
    if not agent_path.exists():
        return None
    pascal = _pascal_name(CURRENT.name)
    upper = re.sub(r"(?<!^)(?=[A-Z])", "_", pascal).upper()
    return {
        "core_dir": core_dir,
        "class": f"{pascal}UnderstandingAgent",
        "state_key": f"{CURRENT.name}_understanding",
        "attr": f"{CURRENT.name}_understanding_agent",
        "node": f"_{CURRENT.name}_understanding_node",
        "graph_node": f"{CURRENT.name}_understanding",
        "empty_const": f"_EMPTY_{upper}_UNDERSTANDING",
    }


def _write_text_if_changed(path: Path, text: str) -> None:
    text = _compact_blank_lines(text)
    old = _compact_blank_lines(path.read_text(encoding="utf-8-sig")) if path.exists() else ""
    if old != text:
        path.write_text(text, encoding="utf-8")


def _ensure_line_after(raw: str, anchor_line: str, new_line: str) -> str:
    """Ensure a line exists after the first matching stripped anchor line."""
    lines = raw.splitlines()
    if any(line.strip() == new_line for line in lines):
        return raw
    for index, line in enumerate(lines):
        if line.strip() == anchor_line:
            lines.insert(index + 1, new_line)
            suffix = "\n" if raw.endswith(("\n", "\r\n")) else ""
            return "\n".join(lines) + suffix
    return raw


def _insert_after_once(raw: str, needle: str, addition: str) -> str:
    return raw if addition.strip() in raw or needle not in raw else raw.replace(
        needle, needle + addition, 1
    )


def _insert_before_once(raw: str, needle: str, addition: str) -> str:
    return raw if addition.strip() in raw or needle not in raw else raw.replace(
        needle, addition + needle, 1
    )


def _insert_after_exact_once(raw: str, needle: str, addition: str) -> str:
    return raw if addition in raw or needle not in raw else raw.replace(
        needle, needle + addition, 1
    )


def _insert_before_exact_once(raw: str, needle: str, addition: str) -> str:
    return raw if addition in raw or needle not in raw else raw.replace(
        needle, addition + needle, 1
    )


def _ensure_before_each(raw: str, needle: str, addition: str) -> str:
    """Ensure addition appears before every occurrence of needle."""
    start = 0
    while True:
        pos = raw.find(needle, start)
        if pos == -1:
            return raw
        window = raw[max(0, pos - 500):pos]
        if addition.strip() not in window:
            raw = raw[:pos] + addition + raw[pos:]
            start = pos + len(addition) + len(needle)
        else:
            start = pos + len(needle)


def write_core_understanding() -> None:
    """自动接入 {domain}_core/{domain}_understanding_agent.py。"""
    info = _core_understanding_info()
    if info is None:
        return

    cls = info["class"]
    attr = info["attr"]
    state_key = info["state_key"]
    node = info["node"]
    graph_node = info["graph_node"]
    empty_const = info["empty_const"]
    state_cls = CURRENT.state_class()
    label = CURRENT.name

    core_init = info["core_dir"] / "__init__.py"
    _write_text_if_changed(
        core_init,
        f'"""{CURRENT.name}核心层。"""\n\n'
        f"from .{CURRENT.name}_understanding_agent import {cls}\n\n"
        f'__all__ = ["{cls}"]\n',
    )

    raw = _read_raw(CURRENT.factory_path)
    raw = _ensure_line_after(
        raw,
        "from perspective import PerspectiveModelingAgent",
        f"from .{CURRENT.name}_core import {cls}",
    )
    raw = _insert_after_exact_once(
        raw,
        '"perspective_modeling_agent": PerspectiveModelingAgent(client),',
        f'\n            "{attr}": {cls}(client),',
    )
    _write_text_if_changed(CURRENT.factory_path, raw)

    raw = _read_raw(CURRENT.models_path)
    raw = _insert_before_once(
        raw,
        "    templates: dict[str, str]",
        f"    {state_key}: dict\n",
    )
    _write_text_if_changed(CURRENT.models_path, raw)

    raw = _read_raw(CURRENT.orch_path)
    raw = _insert_after_exact_once(
        raw,
        f"from .{CURRENT.name}_factory import {_pascal_name(CURRENT.name)}AgentFactory\n",
        f"from .{CURRENT.name}_core import {cls}\n",
    )
    context_line = (
        f'            f"{label}理解：\\n{{_json(state.get(\'{state_key}\'))}}\\n\\n"\n'
    )
    raw = _ensure_before_each(
        raw,
        '            f"原文：\\n{state[\'transcript\']}"',
        context_line,
    )
    raw = _ensure_before_each(
        raw,
        '            f"原文（最高事实来源）：\\n{state[\'transcript\']}\\n\\n"',
        context_line,
    )
    node_code = f'''
    async def {node}(self, state: {state_cls}) -> dict:
        """{label}理解：提取主题、结构、术语和待澄清问题。"""
        try:
            result = await self.{attr}.run(state["transcript"])
        except Exception:
            logger.warning("{label}理解失败，使用空理解继续", exc_info=True)
            return {{
                "{state_key}": {empty_const},
                "quality_degraded": True,
            }}
        return {{"{state_key}": result.model_dump()}}

'''
    # 节点方法已存在（手写或此前已生成）时跳过插入，避免重复定义；
    # 新领域/新 core 未接线时才在渲染上下文生成区之前插入骨架。
    if f"async def {node}" not in raw:
        raw = _insert_before_exact_once(
            raw,
            "    # ── 渲染上下文生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──",
            node_code,
        )
    mount_code = (
        f"        self.{attr}: {cls} = agents[\n"
        f'            "{attr}"\n'
        f"        ]\n"
    )
    raw = _insert_after_exact_once(
        raw,
        '        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[\n'
        '            "perspective_modeling_agent"\n'
        '        ]\n',
        mount_code,
    )
    old_graph = (
        '        builder.add_node(\n'
        '            "perspective_modeling", self._perspective_modeling_node\n'
        '        )\n'
        '        builder.add_edge(START, "perspective_modeling")\n'
        '        core = ["perspective_modeling"]'
    )
    new_graph = (
        f'        builder.add_node("{graph_node}", self.{node})\n'
        '        builder.add_node(\n'
        '            "perspective_modeling", self._perspective_modeling_node\n'
        '        )\n'
        f'        builder.add_edge(START, "{graph_node}")\n'
        '        builder.add_edge(START, "perspective_modeling")\n'
        f'        core = ["{graph_node}", "perspective_modeling"]'
    )
    if old_graph in raw and new_graph not in raw:
        raw = raw.replace(old_graph, new_graph, 1)
    _write_text_if_changed(CURRENT.orch_path, raw)


def check_core_understanding() -> int:
    info = _core_understanding_info()
    if info is None:
        return 0
    checks = [
        (CURRENT.factory_path, info["class"], info["attr"]),
        (CURRENT.models_path, f'{info["state_key"]}: dict'),
        (CURRENT.orch_path, info["class"], info["node"], info["graph_node"]),
        (info["core_dir"] / "__init__.py", info["class"]),
    ]
    rc = 0
    for path, *needles in checks:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = [needle for needle in needles if needle not in text]
        if missing:
            _log(f"{path.name} 缺少 core understanding 接线：{missing}", file=sys.stderr)
            rc = 1
    return rc


# ══════════════════════════════════════════════════════════════
# 合并入口：--write / --check 一次跑完三段
# ══════════════════════════════════════════════════════════════

def _run_write() -> None:
    """段①生成契约：业务模型 + 空结构常量。"""
    _info(f"[1/3] 同步 {CURRENT.name} 的生成模型与空结构常量...")
    models_code, empty_code = gen_generate_all()
    for path, start, end, label in _gen_targets():
        code = models_code if label == "生成模型" else empty_code
        _gen_write_target(path, start, end, code, label)


def _run_write_supervisor() -> None:
    """段②审阅契约：审核模型 + 拒绝态常量。"""
    _info(f"[2/3] 同步 {CURRENT.name} 的审核模型与拒绝兜底...")
    models_code, reject_code = sup_generate_all()
    for path, start, end, label in _sup_targets():
        code = models_code if label == "审核模型" else reject_code
        _sup_write_target(path, start, end, code, label)


def _run_write_factory() -> None:
    """段③装配/注册：装配 / TASK_LINES / 挂载 / 节点映射 / 上下文 / import / 组装器 / fallback。"""
    _info(f"[3/3] 同步 {CURRENT.name} 的任务线装配与运行时编排...")
    lines = find_lines()
    write_core_understanding()
    _fac_write_target(CURRENT.factory_path, generate_lines_code(lines))
    write_core_understanding()
    write_task_skels(lines)
    write_task_lines(CURRENT.orch_path, lines)
    write_mount(CURRENT.orch_path, lines)
    write_node_map(CURRENT.orch_path, lines)
    write_render_context(CURRENT.orch_path, lines)
    write_fallback_imports(CURRENT.orch_path, lines)
    write_line_imports(CURRENT.orch_path, lines)
    write_line_imports(CURRENT.factory_path, lines)
    write_report_imports(CURRENT.orch_path, lines)
    write_report_base_imports(CURRENT.reports_path, lines)
    write_report_validation(CURRENT.models_path, lines)
    write_report_assemblers(CURRENT.orch_path, lines)
    write_fallback_rules(CURRENT.orch_path, lines)
    write_nodes(CURRENT.orch_path, lines)
    write_core_understanding()


def _run_check() -> int:
    """依次校验三段全部生成区，返回聚合退出码。"""
    rc = 0
    models_code, empty_code = gen_generate_all()
    for path, start, end, label in _gen_targets():
        code = models_code if label == "生成模型" else empty_code
        rc |= _gen_check_target(path, start, end, code, label)

    models_code, reject_code = sup_generate_all()
    for path, start, end, label in _sup_targets():
        code = models_code if label == "审核模型" else reject_code
        rc |= _sup_check_target(path, start, end, code, label)

    lines = find_lines()
    rc |= check_core_understanding()
    issues = _runtime_readiness_issues(lines)
    if issues:
        _print_readiness_issues(issues)
        return 1
    rc |= _fac_check_target(CURRENT.factory_path, generate_lines_code(lines))
    rc |= check_task_lines(CURRENT.orch_path, lines)
    rc |= check_mount(CURRENT.orch_path, lines)
    rc |= check_node_map(CURRENT.orch_path, lines)
    rc |= check_render_context(CURRENT.orch_path, lines)
    rc |= check_fallback_imports(CURRENT.orch_path, lines)
    rc |= check_line_imports(CURRENT.orch_path, lines)
    rc |= check_line_imports(CURRENT.factory_path, lines)
    rc |= check_report_imports(CURRENT.orch_path, lines)
    rc |= check_report_base_imports(CURRENT.reports_path, lines)
    rc |= check_report_validation(CURRENT.models_path, lines)
    rc |= check_report_assemblers(CURRENT.orch_path, lines)
    rc |= check_task_skels(lines)
    rc |= check_fallback_rules(CURRENT.orch_path, lines)
    rc |= check_nodes(CURRENT.orch_path, lines)
    return rc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="生成当前领域的全部契约生成区（新增任务线请先跑 register_task.py）"
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="目标领域（src/domain/<name>，含 domain_config）",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write",
        action="store_true",
        help="生成全部生成区（默认动作，可省略）",
    )
    group.add_argument("--check", action="store_true", help="仅校验全部生成区（CI 用）")
    group.add_argument(
        "--model",
        action="store_true",
        help="只生成模型相关内容（业务模型+审核模型+ReportValidation 到 models.py，"
        "并刷新 reports.py 的校验基类 import），不写装配/注册——"
        "两阶段流程第一步：先写 contracts.py 跑这个生成生成/审核模型，"
        "再写 agent/supervisor 等业务类，最后跑全量",
    )
    args = parser.parse_args(argv)

    try:
        set_domain(args.domain)

        if args.check:
            _info(f"检查 domain/{args.domain} 的生成区一致性...")
            rc = _run_check()
            if rc != 0:
                print("CHECK FAILED: 生成区或任务线文件还不完整。", file=sys.stderr)
                print(
                    f"建议先运行：python tools/scripts/sync_domain.py --domain {args.domain}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"SUCCESS! domain/{args.domain} 生成区检查通过。")
            return

        # 默认动作 = --write（可省略显式传入）
        _run_write()
        _run_write_supervisor()
        if args.model:
            lines = find_lines()
            write_report_validation(CURRENT.models_path, lines)
            write_report_base_imports(CURRENT.reports_path, lines)
        else:
            issues = _runtime_readiness_issues(find_lines())
            if issues:
                _print_readiness_issues(issues)
                print("PARTIAL: models.py 已同步，运行时装配尚未写入。")
                sys.exit(2)
            _run_write_factory()
        print(f"SUCCESS! domain/{args.domain} 已同步完成。")
    except SystemExit as e:
        # 失败：stdout 只输出 FAIL!!!；细节（sys.exit 的消息）留给 stderr
        if isinstance(e.code, int):
            rc = e.code
        else:
            _log(e.code, file=sys.stderr)
            rc = 1
        print("FAIL!!!")
        sys.exit(rc)
    except Exception:
        # 非 SystemExit 异常（如路径不存在）：打印 traceback，方便定位脚手架问题。
        traceback.print_exc(file=sys.stderr)
        print("FAIL!!!")
        sys.exit(1)


if __name__ == "__main__":
    main()
