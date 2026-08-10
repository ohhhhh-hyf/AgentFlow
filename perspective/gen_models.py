"""gen_models.py —— perspective 公共包的迷你模型生成器。

读取 contracts.py 的 PerspectiveModelingGenerationContract，复用
tools/scripts/codegen.py 的生成函数（parse_generation_contract /
generate_generation_model / generate_empty_constants），重写
models.py 的模型生成区（模型类 + EMPTY_PERSPECTIVE_MODELING 空结构常量）。

用法：python perspective/gen_models.py

改字段流程：只改 contracts.py 的 fields → 运行本脚本
→ 模型声明 / validate / 空常量 自动同步（与 codegen 生成风格一致）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.contracts import GenerationContract  # noqa: E402
from tools.scripts.codegen import (             # noqa: E402
    generate_empty_constants,
    generate_generation_model,
    parse_generation_contract,
)

PACKAGE = Path(__file__).resolve().parent

ZONE_START = "# ── 模型生成区：由 perspective/gen_models.py 生成，勿手改 ──"
ZONE_END = "# ── 模型生成区结束 ──"


def _load_module(path: Path):
    """按文件路径直接加载模块（绕过包 __init__ 链，避免连锁 import）。

    使用唯一模块名注册，避免与其他包的同名 contracts 模块冲突。
    """
    mod_name = f"_perspective_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载模块：{path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _find_contract(mod):
    """找到模块中唯一的 GenerationContract 子类。"""
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, GenerationContract)
            and obj is not GenerationContract
        ):
            return obj
    raise SystemExit("perspective/contracts.py 未找到 GenerationContract 子类")


def _gen_zone_code(cls: type) -> str:
    """从契约类生成模型 + 空结构常量代码（与 codegen 输出风格一致）。"""
    model_cls = cls.__name__.removesuffix("GenerationContract")
    fields = parse_generation_contract(cls)
    model_code = generate_generation_model(model_cls, fields)
    # 公共包导出用公开名：_EMPTY_PERSPECTIVE_MODELING → EMPTY_PERSPECTIVE_MODELING
    empty_code = generate_empty_constants(model_cls, fields).replace(
        "_EMPTY_", "EMPTY_"
    )
    return model_code + "\n\n\n" + empty_code


def main() -> None:
    contracts_path = PACKAGE / "contracts.py"
    if not contracts_path.exists():
        raise SystemExit(f"{contracts_path} 不存在")
    cls = _find_contract(_load_module(contracts_path))
    code = _gen_zone_code(cls)

    models_path = PACKAGE / "models.py"
    raw = models_path.read_text(encoding="utf-8")
    if ZONE_START not in raw or ZONE_END not in raw:
        raise SystemExit(
            f"{models_path.name} 中未找到模型生成区标记。请先手动添加：\n"
            f"{ZONE_START}\n（现有内容移入此处）\n{ZONE_END}"
        )
    nl = "\r\n" if "\r\n" in raw else "\n"
    code_block = nl.join(code.split("\n"))
    block = ZONE_START + nl + nl + code_block + nl + nl + nl + ZONE_END
    # 切片替换生成区（不依赖正则匹配空/非空内容，始终可靠）
    start_idx = raw.index(ZONE_START)
    end_idx = raw.index(ZONE_END) + len(ZONE_END)
    new_raw = raw[:start_idx] + block + raw[end_idx:]
    models_path.write_text(new_raw, encoding="utf-8")
    print("SUCCESS!")


if __name__ == "__main__":
    main()
