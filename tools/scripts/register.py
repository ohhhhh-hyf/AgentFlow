"""register.py —— 新增任务线第一步：注册 + 四件套骨架 + 工厂 import。

用法：python register.py --domain meeting --task risk --name "风险"

自动做：
1. domain_config.py 的 LINE_CN_NAMES 追加 ``"risk": "风险",``（幂等，已存在则跳过）
2. 创建 tasks/risk/ 四件套骨架（risk_agent.py / risk_supervisor.py / risk_render.py / __init__.py）
3. meeting_factory.py 任务线 import 生成区（自动含新线）

之后手写 models.py 的 RiskReport 类，再跑 codegen.py --domain meeting 全量生成。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codegen import (  # noqa: E402
    CURRENT,
    find_lines,
    set_domain,
    write_factory_line_imports,
    write_report_base_imports,
    write_report_validation,
    write_task_skels,
)


def _register_line(task: str, name: str) -> None:
    """把任务线注册写进当前领域的 domain_config.py（LINE_CN_NAMES 追加一行）。

    幂等：线名已存在则跳过。用 ast 定位 LINE_CN_NAMES 的 dict 字面量，
    在其结束行（``}``）前插入 ``    "线名": "中文名",``，保留文件其余内容。
    """
    path = CURRENT.dir / "domain_config.py"
    if not path.exists():
        raise SystemExit(f"{path} 不存在——请先创建领域骨架（含 domain_config.py）")
    raw = path.read_text(encoding="utf-8")
    tree = ast.parse(raw)
    dict_node = None
    target_name = None
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "LINE_CN_NAMES"
        ):
            dict_node, target_name = node.value, node.target.id
            break
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "LINE_CN_NAMES" for t in node.targets
        ):
            dict_node, target_name = node.value, node.targets[0].id
            break
    if not isinstance(dict_node, ast.Dict):
        raise SystemExit(f"{path} 未找到 LINE_CN_NAMES 的 dict 定义")
    keys = [k.value for k in dict_node.keys if k is not None]
    if task in keys:
        return  # 幂等：已注册
    lines = raw.split("\n")
    if dict_node.end_lineno == dict_node.lineno:
        # 单行 dict（LINE_CN_NAMES = {}）→ 展开为多行
        lines[dict_node.end_lineno - 1] = (
            f'{target_name}: dict[str, str] = {{\n    "{task}": "{name}",\n}}'
        )
    else:
        lines.insert(dict_node.end_lineno - 1, f'    "{task}": "{name}",')
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="新增任务线第一步：注册 LINE_CN_NAMES + 四件套骨架 + 工厂 import"
    )
    parser.add_argument(
        "--domain", required=True, help="目标领域（domain/<name>，含 domain_config）"
    )
    parser.add_argument("--task", required=True, metavar="线名", help="任务线目录名，如 risk")
    parser.add_argument("--name", required=True, metavar="中文名", help="任务线中文名，如 风险")
    args = parser.parse_args()

    try:
        set_domain(args.domain)
        _register_line(args.task, args.name)
        lines = find_lines()
        write_task_skels(lines)
        write_report_validation(CURRENT.models_path, lines)
        write_report_base_imports(CURRENT.reports_path, lines)
        write_factory_line_imports(lines)
        print("SUCCESS!")
    except SystemExit as e:
        # 失败：stdout 只输出 FAIL!!!；细节（sys.exit 的消息）留给 stderr
        if isinstance(e.code, int):
            rc = e.code
        else:
            print(e.code, file=sys.stderr)
            rc = 1
        print("FAIL!!!")
        sys.exit(rc)
    except Exception:
        # 非 SystemExit 异常（如路径不存在）：traceback 到 stderr，stdout 只 FAIL!!!
        print("FAIL!!!")
        sys.exit(1)


if __name__ == "__main__":
    main()
