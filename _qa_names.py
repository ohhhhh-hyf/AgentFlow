# -*- coding: utf-8 -*-
"""Q&A 称呼按「确定度」回退：不确定就不写名字（a 模板 b 全局规则 c 媒体问答）。

a) media_briefing [Q&A环节]：提问方/回应方按确定度回退
b) body_rules.py 成员称呼条：补「必须能确定对应的就是本次提问/回应的人」
c) media_qa_session [核心提问与回应]：同一口径
"""
import pathlib
import re

# ---------- a) media_briefing ----------
P1 = pathlib.Path("template_v3/media_briefing.md")
r1 = P1.read_bytes().decode("utf-8")
A_OLD = (
    "提问方写「媒体名＋姓名/记者」（原文任何位置出现过姓名就必须用，"
    "**不得用「主持人」「发言人」顶替已知姓名**）；**回应方能确定姓名就写姓名**"
    "（全篇统一用同一个称呼；只有确实没有姓名时才写「**答**」）；"
)
A_NEW = (
    "**提问方按确定度回退**：能确定到人才写「媒体名＋姓名」或「姓名」；只知道媒体名就只写媒体名；"
    "只知道角色就写「记者」；**都不确定就不写名字、写成「问」**——"
    "**不得把原文别处出现过的姓名安到本次提问上**（**不得用「主持人」「发言人」顶替已知姓名**）；"
    "**回应方能确定姓名才写姓名**（全篇统一用同一个称呼；不能确定就写「**答**」）；"
)
assert r1.count(A_OLD) == 1
P1.write_bytes(re.sub(rb"\r?\n", b"\r\n", r1.replace(A_OLD, A_NEW).encode("utf-8")))
print("a) media_briefing 改完")

# ---------- b) body_rules ----------
P2 = pathlib.Path("tools/templates/body_rules.py")
r2 = P2.read_bytes().decode("utf-8")
B_OLD = "没有支撑的一律按上述顺序回退。"
B_NEW = (
    "没有支撑的一律按上述顺序回退。**并且问答/对话中的姓名还要能确定对应的就是本次提问或回应的人**"
    "——只是原文别处出现过、但无法确定对应关系的，**不得使用**（按回退链退到媒体名、角色、编号或「问」「答」）。"
)
assert r2.count(B_OLD) == 1
P2.write_bytes(r2.replace(B_OLD, B_NEW).encode("utf-8"))
print("b) body_rules 改完")

# ---------- c) media_qa_session ----------
P3 = pathlib.Path("template_v3/media_qa_session.md")
r3 = P3.read_bytes().decode("utf-8")
C_OLD = (
    "提问方写「媒体名＋姓名/记者」（原文任何位置出现过姓名就必须用，"
    "**不得用「记者」「发言人」顶替已知姓名**）；**回应方能确定姓名就写姓名**"
    "（全篇统一用同一个称呼；只有确实没有姓名时才写「**答**」）；"
)
C_NEW = (
    "**提问方按确定度回退**：能确定到人才写「媒体名＋姓名」或「姓名」；只知道媒体名就只写媒体名；"
    "只知道角色就写「记者」；**都不确定就不写名字、写成「问」**——"
    "**不得把原文别处出现过的姓名安到本次提问上**（**不得用「记者」「发言人」顶替已知姓名**）；"
    "**回应方能确定姓名才写姓名**（全篇统一用同一个称呼；不能确定就写「**答**」）；"
)
assert r3.count(C_OLD) == 1
P3.write_bytes(re.sub(rb"\r?\n", b"\r\n", r3.replace(C_OLD, C_NEW).encode("utf-8")))
print("c) media_qa_session 改完")

# ---------- 守卫同步 ----------
G = pathlib.Path("tools/template_router/_selftest.py")
g = G.read_bytes().decode("utf-8")
pairs = [
    ('        check(f"{name}：回应方能确定姓名就写姓名（「答」只作无姓名兜底）",\r\n'
     '              "回应方能确定姓名就写姓名" in spec and "只有确实没有姓名时才写" in spec\r\n'
     '              and "全篇统一用同一个称呼" in spec\r\n'
     '              and "首次写全" not in spec, "")',
     '        check(f"{name}：回应方能确定姓名才写姓名（「答」只作无姓名兜底）",\r\n'
     '              "回应方能确定姓名才写姓名" in spec and "不能确定就写「**答**」" in spec\r\n'
     '              and "全篇统一用同一个称呼" in spec\r\n'
     '              and "首次写全" not in spec, "")'),
    ('        check(f"{name}：提问方姓名优先写成硬口径（原文出现过就必须用）",\r\n'
     '              "原文任何位置出现过姓名就必须用" in spec, "")',
     '        check(f"{name}：提问方按确定度回退（不确定就不写名字）",\r\n'
     '              "**提问方按确定度回退**" in spec\r\n'
     '              and "都不确定就不写名字、写成「问」" in spec\r\n'
     '              and "不得把原文别处出现过的姓名安到本次提问上" in spec, "")'),
    ('    check("全局称呼规则：问答用名必须有问答段之外的支撑（无支撑退角色）",\r\n'
     '          "问答/对话中使用的姓名必须有支撑" in rule\r\n'
     '          and "在问答段之外的原文里出现过" in rule, "")',
     '    check("全局称呼规则：问答用名必须有问答段之外的支撑（无支撑退角色）",\r\n'
     '          "问答/对话中使用的姓名必须有支撑" in rule\r\n'
     '          and "在问答段之外的原文里出现过" in rule, "")\r\n'
     '    check("全局称呼规则：还要能确定对应的就是本次提问/回应的人（不确定不得用）",\r\n'
     '          "还要能确定对应的就是本次提问或回应的人" in rule\r\n'
     '          and "但无法确定对应关系的，**不得使用**" in rule, "")'),
]
for old, new in pairs:
    n = g.count(old)
    print(("守卫 OK " if n == 1 else "守卫 SKIP(%d) " % n) + old[:44].replace("\r\n", "⏎"))
    assert n == 1, old[:70]
    g = g.replace(old, new)
G.write_bytes(g.encode("utf-8"))
print("守卫改完")
