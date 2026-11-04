"""断言助手：失败必须抛异常，由 pytest 判定。"""
from __future__ import annotations


def expect(condition: bool, message: str, detail: object = "") -> None:
    """条件为假时抛出 ``AssertionError``。

    用于替代历史上只把结果追加到 ``PASS``/``FAIL`` 列表并 print 的 ``check()``；
    后者在 pytest 下永远不会让测试变红。``detail`` 可选，失败时附在消息后面。
    """
    if condition:
        return
    raise AssertionError(message if not detail else f"{message} | {detail}")
