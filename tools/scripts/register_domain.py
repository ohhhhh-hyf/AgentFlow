"""register_domain.py —— 新建领域骨架：目录 + 骨架文件 + 生成区填充。

用法：python register_domain.py --domain notes --name "笔记" [--state NotesState]

自动做：
1. 创建 domain/{domain}/ 目录（tasks/ {domain}_core/ samples/ 空骨架）
2. 从 tools/scripts/domain_template/ 渲染 6 个骨架文件
   （orchestrator / models / reports / {domain}_factory / domain_config / __init__）
3. 内置视角建模（perspective 公共组件：节点 + agent 挂载 + state 字段）
4. 内部调用 sync_domain 填充全部生成区（等价于跑 sync_domain.py --domain {domain}）
5. 校验生成区一致性（等价于 --check）

之后即可用既有链路添加任务线：
    register_task.py --domain {domain} --task xxx --name "中文名"
    → 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
    → sync_domain.py --domain {domain} → --check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_domain import (  # noqa: E402
    _run_check,
    _run_write,
    _run_write_factory,
    _run_write_supervisor,
    set_domain,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = Path(__file__).resolve().parent / "domain_template"

# 模板文件名 → 目标文件名（orchestrator 的导出名随领域名）
TPL_FILES = [
    ("orchestrator.tpl.py", "orchestrator.py"),
    ("models.tpl.py", "models.py"),
    ("reports.tpl.py", "reports.py"),
    ("factory.tpl.py", None),  # -> {domain}_factory.py
    ("domain_config.tpl.py", "domain_config.py"),
    ("__init__.tpl.py", "__init__.py"),
]


def _pascal(domain: str) -> str:
    return domain[0].upper() + domain[1:]


def _render(text: str, domain: str, name: str, state: str) -> str:
    return (
        text.replace("{{DOMAIN}}", domain)
        .replace("{{PASCAL}}", _pascal(domain))
        .replace("{{STATE_CLASS}}", state)
        .replace("{{CN_NAME}}", name)
    )


def _scaffold(domain: str, name: str, state: str) -> None:
    domain_dir = ROOT / "domain" / domain
    if domain_dir.exists():
        raise SystemExit(f"domain/{domain} 已存在——拒绝覆盖（幂等保护）")

    (domain_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (domain_dir / f"{domain}_core").mkdir(parents=True, exist_ok=True)
    (domain_dir / "samples").mkdir(parents=True, exist_ok=True)

    for tpl_name, out_name in TPL_FILES:
        src = TEMPLATE_DIR / tpl_name
        if not src.exists():
            raise SystemExit(f"模板缺失：{src}")
        text = _render(src.read_text(encoding="utf-8"), domain, name, state)
        if out_name is None:
            out_name = f"{domain}_factory.py"
        (domain_dir / out_name).write_text(text, encoding="utf-8")

    (domain_dir / "tasks" / "__init__.py").write_text(
        f'"""tasks —— {name}的任务线。"""\n', encoding="utf-8"
    )
    core_init = (
        f'"""{name}核心层。\n\n'
        f'视角建模（perspective 公共组件）已由脚手架内置：'
        f'orchestrator 的 _perspective_modeling_node 自动挂载、'
        f'{domain}_factory 已组装 PerspectiveModelingAgent、'
        f'state 已含 perspective_profile 字段，无需重复实现。\n'
        f'领域专属核心 Agent（如"{name}理解"）在此编写并接入 '
        f'{domain}_factory.py 与 orchestrator.py。\n"""\n'
    )
    (domain_dir / f"{domain}_core" / "__init__.py").write_text(
        core_init, encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="新建领域骨架（register_domain）")
    parser.add_argument("--domain", required=True, help="领域目录名（如 notes）")
    parser.add_argument("--name", required=True, help="领域中文名（如 笔记）")
    parser.add_argument(
        "--state", default=None, help="state 类名（默认 {Pascal}State）"
    )
    args = parser.parse_args()

    domain = args.domain.strip()
    if not domain.isidentifier():
        raise SystemExit(f"非法领域名：{domain!r}（需为合法 Python 标识符）")
    name = args.name.strip()
    state = args.state or f"{_pascal(domain)}State"

    print(f"[1/3] 创建 domain/{domain} 目录骨架...")
    _scaffold(domain, name, state)

    # 填充生成区（等价 sync_domain --domain {domain} 的写入）+ 校验
    set_domain(domain)
    print("[2/3] 初始化生成区...")
    _run_write()
    _run_write_supervisor()
    _run_write_factory()
    print("[3/3] 校验生成区...")
    rc = _run_check()
    if rc != 0:
        raise SystemExit("生成区填充后校验失败——请检查模板生成区标记")

    print(f"SUCCESS! 已创建 domain/{domain} 骨架（中文名：{name}，state：{state}）")
    print("内置：视角建模（perspective 公共组件）已自动挂载")
    print("下一步：")
    print(f"  1. 可选：在 domain/{domain}/{domain}_core/ 下添加 {domain}_understanding_agent.py")
    print(f"  2. python tools/scripts/sync_domain.py --domain {domain}")
    print(
        f'  3. python tools/scripts/register_task.py --domain {domain} '
        f'--task xxx --name "中文名"'
    )
    print("  4. 补齐 task 的 contracts/prompts/steps 和 reports.py")
    print(f"  5. python tools/scripts/sync_domain.py --domain {domain}")
    print(f"  6. python tools/scripts/sync_domain.py --domain {domain} --check")


if __name__ == "__main__":
    main()
