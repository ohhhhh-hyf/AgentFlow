# -*- coding: utf-8 -*-
"""P2 收尾：natural_key 文件名数字序回归测试。

运行：python ocr_baseline/test_step7.py（零网络）。
背景：旧实现对完整文件名（以 .jpg 结尾）匹配 r"(\d+)\s*$" 永远失败，
natural_key 静默退化为字典序，页面顺序变成 1,10,…,19,2,… 的错序。
验证点：剥离扩展名后按末段数字排序；.jpeg/.png 同规则；无数字名稳定回退。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ocr_baseline.run_baseline import natural_key  # noqa: E402


def main() -> None:
    names = ["U202314751_%d.jpg" % i for i in range(1, 22)]
    ordered = sorted(names, key=natural_key)
    expect = ["U202314751_%d.jpg" % i for i in range(1, 22)]
    assert ordered == expect, ordered[:5]
    print("PASS 21 张按 1..21 数字序")

    # 前缀含其它数字段（相册 id）不影响：取的是扩展名前的末段数字
    assert natural_key("U202314751_2.jpg") < natural_key("U202314751_10.jpg")
    assert natural_key("IMG_0042.png") < natural_key("IMG_0100.png")
    assert natural_key("p9.jpeg") < natural_key("p10.jpeg")
    print("PASS .jpg/.jpeg/.png 与多数字段名")

    # 无尾数字段 → 稳定回退（与旧行为一致，不抛异常）
    ks = sorted(["page_a.jpg", "page_b.jpg"], key=natural_key)
    assert ks == ["page_a.jpg", "page_b.jpg"]
    print("PASS 无数字名稳定回退")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
