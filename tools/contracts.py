"""contracts.py —— 审阅契约构件类（Decision / Check / Feedback / SupervisorContract）。

开发者用这些类在 ``prompts.py`` 里声明审阅契约，替代手写 JSON 字符串：

    class MinutesSupervisorContract(SupervisorContract):
        decision = Decision()
        feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
        checks = [
            Check("facts_check", "仅记录严重问题，轻微问题不记录"),
            Check("perspective_check", "仅记录严重问题"),
            Check("consistency_check", "仅记录严重问题"),
        ]

类定义时自动在所在模块注册同名输出常量（名称与旧字符串契约完全一致，
现有 ``from .prompts import MINUTES_SUPERVISOR_OUTPUT_CONTRACT`` 无需改动）：

    MINUTES_SUPERVISOR_OUTPUT_CONTRACT = <to_json_template() 的 JSON 文本>

该常量一物两用：
- 运行时：``client.structured(..., output_contract=...)`` 拼进 system prompt，
  作为 LLM 的"唯一合法输出模板"
- 脚本期：``codegen.py`` import 契约类读结构（checks / decision /
  feedback），生成审核模型 + 拒绝态兜底常量
"""
from __future__ import annotations

import re
import sys
from typing import ClassVar


class Decision:
    """审核决策枚举（固定三值，与 validate_supervisor_semantics 对齐）。"""

    values: tuple[str, ...] = ("approve", "revise", "reject")


class Check:
    """检查项：``{status: pass|fail, findings: [...]}`` 形状。

    Args:
        name: 检查项字段名（如 ``"facts_check"``），也是生成的审核模型字段名。
        desc: 给 LLM 的 findings 填写说明（进 prompt 模板，不参与模型生成）。
    """

    def __init__(self, name: str, desc: str = "仅记录严重问题") -> None:
        if not name or not name.isidentifier():
            raise ValueError(f"检查项名称必须是合法标识符：{name!r}")
        self.name = name
        self.desc = desc


class Feedback:
    """返工意见字段（字符串数组）。

    Args:
        desc: 给 LLM 的 feedback 填写说明（进 prompt 模板，不参与模型生成）。
    """

    def __init__(self, desc: str = "") -> None:
        self.desc = desc


class SupervisorContract:
    """审阅契约基类。

    子类声明 ``decision`` / ``feedback`` / ``checks`` 三个类属性；类定义时
    ``__init_subclass__`` 自动在所在模块注册 ``{基名大写}_SUPERVISOR_OUTPUT_CONTRACT``
    常量（基名 = 类名去 ``SupervisorContract`` 后缀），值为 ``to_json_template()``。
    """

    decision: ClassVar[Decision] = Decision()
    feedback: ClassVar[Feedback] = Feedback()
    checks: ClassVar[list[Check]] = []

    @classmethod
    def to_json_template(cls) -> str:
        """序列化为 LLM 输出模板（JSON 文本），供 structured() 拼进 system prompt。"""
        lines = ["{"]
        lines.append(f'  "decision": "{"|".join(cls.decision.values)}",')
        for ck in cls.checks:
            lines.append(f'  "{ck.name}": {{')
            lines.append('    "status": "pass|fail",')
            lines.append(f'    "findings": ["{ck.desc}"]')
            lines.append("  },")
        lines.append(f'  "feedback": ["{cls.feedback.desc}"]')
        lines.append("}")
        return "\n".join(lines)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # 仅做命名与结构校验；输出常量（{基名大写}_SUPERVISOR_OUTPUT_CONTRACT）
        # 由契约所在目录的 contracts.py 显式赋值：
        #     MINUTES_SUPERVISOR_OUTPUT_CONTRACT = MinutesSupervisorContract.to_json_template()
        name = cls.__name__
        suffix = "SupervisorContract"
        if not name.endswith(suffix) or len(name) == len(suffix):
            raise ValueError(
                f"审阅契约类命名不符合规范：{name!r}\n"
                f"必须命名为 {{线名}}{suffix}（如 MinutesSupervisorContract）"
            )
        if not cls.checks:
            raise ValueError(f"{name} 必须至少声明一个检查项（checks 非空）")


__all__ = ["Check", "Decision", "Feedback", "SupervisorContract"]


# ── 生成契约构件与基类 ────────────────────────────────────────

class Field:
    """生成契约字段基类。

    Args:
        name: 字段名（生成的模型字段名 + LLM 输出 JSON 键名）。
        desc: 给 LLM 的填写说明/示例值（进 prompt 模板，不参与模型校验）。
    """

    def __init__(self, name: str, desc: str = "") -> None:
        if not name or not name.isidentifier():
            raise ValueError(f"字段名必须是合法标识符：{name!r}")
        self.name = name
        self.desc = desc

    @property
    def kind(self) -> str:  # pragma: no cover - 由子类覆盖
        raise NotImplementedError


class StrField(Field):
    """字符串字段。"""

    @property
    def kind(self) -> str:
        return "str"



class EnumField(Field):
    """枚举字段（JSON 值形如 ``"high|medium|low"``）。"""

    def __init__(self, name: str, values: list[str], desc: str = "") -> None:
        super().__init__(name, desc)
        if not values:
            raise ValueError(f"枚举字段 {name} 的 values 不能为空")
        self.values = list(values)

    @property
    def kind(self) -> str:
        return "enum"


class StrListField(Field):
    """字符串数组字段。"""

    @property
    def kind(self) -> str:
        return "str_list"


class ObjField(Field):
    """嵌套对象字段（elements 描述内部结构，浅校验不展开）。"""

    def __init__(self, name: str, elements: list[Field] | None = None,
                 desc: str = "") -> None:
        super().__init__(name, desc)
        self.elements = list(elements or [])

    @property
    def kind(self) -> str:
        return "dict"


class ObjListField(ObjField):
    """对象数组字段（elements 描述元素结构；空 elements = 空数组）。"""

    @property
    def kind(self) -> str:
        return "obj_list"


class GenerationContract:
    """生成契约基类。

    子类声明 ``fields``（Field 列表）；输出模板常量
    （{基名大写}_GENERATION_OUTPUT_CONTRACT）由契约所在目录的 contracts.py
    显式赋值：``MINUTES_GENERATION_OUTPUT_CONTRACT = MinutesGenerationContract.to_json_template()``
    """

    fields: ClassVar[list[Field]] = []

    @classmethod
    def to_json_template(cls) -> str:
        """序列化为 LLM 输出模板（JSON 文本），供 structured() 拼进 system prompt。"""
        lines = ["{"]
        for i, f in enumerate(cls.fields):
            comma = "," if i < len(cls.fields) - 1 else ""
            lines.append(f'  "{f.name}": {cls._value_json(f)}{comma}')
        lines.append("}")
        return "\n".join(lines)

    @classmethod
    def _value_json(cls, f: Field) -> str:
        if isinstance(f, StrField):
            return f'"{f.desc}"'
        if isinstance(f, EnumField):
            return f'"{ "|".join(f.values) }"'
        if isinstance(f, StrListField):
            return f'["{f.desc}"]'
        if isinstance(f, ObjListField):
            if not f.elements:
                return "[]"
            inner = ",\n".join(
                f'      "{e.name}": {cls._value_json(e)}' for e in f.elements
            )
            return "[\n    {\n" + inner + "\n    }\n  ]"
        if isinstance(f, ObjField):
            inner = ",\n".join(
                f'      "{e.name}": {cls._value_json(e)}' for e in f.elements
            )
            return "{\n    " + inner.replace(",\n", ",\n    ") + "\n  }"
        raise ValueError(f"未知字段类型：{type(f).__name__}")

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        name = cls.__name__
        suffix = "GenerationContract"
        if not name.endswith(suffix) or len(name) == len(suffix):
            raise ValueError(
                f"生成契约类命名不符合规范：{name!r}\n"
                f"必须命名为 {{线名/功能}}{suffix}（如 MinutesGenerationContract）"
            )
        if not cls.fields:
            raise ValueError(f"{name} 必须至少声明一个字段（fields 非空）")
        seen: set[str] = set()
        for f in cls.fields:
            if f.name in seen:
                raise ValueError(f"{name} 字段名重复：{f.name}")
            seen.add(f.name)


__all__ = [
    "Check", "Decision", "EnumField", "Feedback", "Field",
    "GenerationContract", "ObjField", "ObjListField", "StrField",
    "StrListField", "SupervisorContract",
]
