"""自检 ``data/{user_id}/user.json`` 是否被正确解析与注入（**不调模型**，秒级）。

用法::

    python tools/devtools/check_user_profile.py            # 默认 user_id=1 / domain=meeting
    python tools/devtools/check_user_profile.py 2          # 指定用户
    python tools/devtools/check_user_profile.py 1 --show-block   # 顺带打印两个注入块全文

检查四件事：
1. ``extra.profile="user"`` 指向这份档案（``profile`` 传空是默认档＝客观全员，不读档案）；
2. 档案有没有被判成"真人"（``persona_type`` 是否为空）、``role_template`` 有没有合并进来；
3. 注入理解层的「本用户称呼」和注入纪要线的「本用户偏好」长什么样；
4. 按保守口径，这次会跑视角建模还是跳过（有可扫关注域 → 跑）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import profile_path  # noqa: E402
from domain.meeting.models_base import UserIdentity  # noqa: E402
from perspective import (  # noqa: E402
    build_preference_block,
    build_user_channel,
)
from perspective.synth import _has_scan_scope  # noqa: E402
from tools.core.profiles import (  # noqa: E402
    filter_identity_fields,
    read_user_profile,
    resolve_role_template,
    sanitize_user_profile,
)


def main(argv: list[str]) -> int:
    user_id = next((a for a in argv[1:] if not a.startswith("-")), "1")
    show_block = "--show-block" in argv

    picked = profile_path("meeting", "user", user_id)
    print(f"① extra.profile=\"user\" → {picked or '（空：档案缺失/非法，接口会 400）'}")
    if not str(picked) or not Path(picked).is_file():
        print("   ✗ 没找到可用档案：放好 data/{user_id}/user.json 后重跑")
        return 1
    empty_pick = profile_path("meeting", "", user_id)
    print(f"   （对照）extra.profile 传空 → {empty_pick}（默认档＝客观全员，不读档案）")

    raw = read_user_profile(picked)
    if raw is None:
        print("   ✗ 档案不合法（需要 JSON 对象 + 非空 name）→ 运行时会按无档案处理")
        return 1
    profile = UserIdentity(
        **filter_identity_fields(
            resolve_role_template(sanitize_user_profile(raw), Path(picked).parent),
            UserIdentity,
        )
    )
    print("② 解析后的画像：")
    print(f"   name = {profile.name} | role = {profile.role} | department = {profile.department}")
    print(f"   persona_type = {profile.persona_type!r}（None/空 = 真人）| role_template = {profile.role_template}")
    print(f"   别名 = {profile.name_aliases}")
    print(f"   focus_areas（{len(profile.focus_areas)} 条）= {profile.focus_areas[:3]}{' …' if len(profile.focus_areas) > 3 else ''}")
    print(f"   responsibilities（{len(profile.responsibilities)} 条）")
    print(f"   preferences（{len(profile.preferences)} 条）| personality = {profile.personality!r}")

    channel = build_user_channel(profile.model_dump())
    preference = build_preference_block(profile.model_dump())
    print(f"③ 称呼表：{'已生成' if channel else '（不注入：客观/职业模板/无姓名）'} | 偏好块：{'已生成' if preference else '（无可用偏好）'}")
    if show_block:
        print("\n--- 称呼表 ---\n" + (channel or "（空）"))
        print("\n--- 偏好块 ---\n" + (preference or "（空）"))

    scan = _has_scan_scope(profile.model_dump())
    print(
        "④ 单跑纪要时的判定："
        + ("**会跑视角建模**（画像里有可扫关注域：关注域内、没点他名的条目只有建模能捞）" if scan
           else "跳过建模，程序合成视角模型（极简画像）")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
