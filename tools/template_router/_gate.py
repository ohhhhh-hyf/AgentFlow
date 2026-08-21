"""tools.template_router.gate —— 模板路由·门禁层：输出校验、保真检查与自然语言模板编译。"""
from __future__ import annotations

from __future__ import annotations
import hashlib
import json
import logging
import re
from typing import Any

from ._base import _COMPILE_CACHE, _COMPILE_CACHE_VERSION, _COMPILE_FAIL_COUNTS, _COMPILE_FAIL_SKIP_THRESHOLD, _EXPANSION_GUARDS, _MODIFY_SYSTEM, _PLACEHOLDER_RE, _client_text, _hint_clean, _strip_heading_number, _table_topic_from_context, is_router_enabled, logger, strip_outer_markdown_fence
from ._detect import _looks_like_placeholder, _table_row_limit_from_text, detect_template_kind, extract_description_cues, parse_placeholder_template
from ._placeholder import _is_table_data_row, template_to_preview
from ._preview import _aspect_has_fixed_heading, _aspect_has_own_slot, extract_listed_aspects

logger = logging.getLogger(__name__)


def validate_rendered_output(
    rendered: str,
    template: str,
    kind: str | None = None,
) -> list[str]:
    """校验渲染输出，返回错误列表；空列表 = 通过。

    - 类型一：残留 ``[占位符]`` 检测 + 固定文字完整性（长度≥4 的固定段）
    - 类型二：模板声明 JSON/数组且输出以 ``[`` 开头时校验 JSON 合法性
    """
    errors: list[str] = []
    if not rendered or not rendered.strip():
        return ["渲染输出为空"]
    kind = kind or detect_template_kind(template)
    if kind == "placeholder":
        leftovers = [
            f"[{m.group(1)[:20]}]".replace("\n", " ")
            for m in _PLACEHOLDER_RE.finditer(rendered)
            if _looks_like_placeholder(
                m.group(1), next_char=rendered[m.end() : m.end() + 1]
            )
        ][:5]
        if leftovers:
            errors.append(f"输出残留占位符：{'、'.join(leftovers)}")
        segments = parse_placeholder_template(template)
        fixed = []
        for s in segments:
            if s["kind"] != "text":
                continue
            raw = s["text"].strip()
            if len(raw) < 4:
                continue
            # 空表行/仅竖线空白（如「| | | | | |」）不算必须保留的固定文案
            if not re.sub(r"[\s|:\-]+", "", raw):
                continue
            fixed.append(raw)
        # 归一化空白后再比对，避免换行差异误报
        rendered_norm = re.sub(r"\s+", " ", rendered)
        missing_fixed = 0
        for text in fixed:
            text_norm = re.sub(r"\s+", " ", text)
            if text not in rendered and text_norm not in rendered_norm:
                missing_fixed += 1
                if missing_fixed <= 2:
                    errors.append(f"模板固定文字丢失：{text[:30]!r}")
        if missing_fixed > 2:
            errors.append(f"另有 {missing_fixed - 2} 处固定文字缺失")
    elif kind == "spec":
        stripped = rendered.strip()
        # 允许被 ``` 包裹
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
            stripped = stripped.strip()
        if ("JSON" in template or "数组" in template) and (
            stripped.startswith("[") or stripped.startswith("{")
        ):
            try:
                json.loads(stripped)
            except Exception as exc:
                errors.append(f"输出不是合法 JSON：{exc}")
    return errors


def check_compile_fidelity(description: str, compiled: str) -> list[str]:
    """检查编译结果是否忠实于用户描述；返回问题列表（空=通过）。"""
    issues: list[str] = []
    if not compiled or not compiled.strip():
        return ["编译结果为空"]
    if detect_template_kind(compiled) != "placeholder":
        return ["编译结果不是占位符模板"]
    segments = parse_placeholder_template(compiled)
    fields = [s for s in segments if s["kind"] == "field"]
    if not fields:
        issues.append("编译结果未包含可填充占位符")

    cues = extract_description_cues(description)
    flags: set[str] = cues["flags"]
    compiled_l = compiled

    # 用户用顿号/与/和/及并列的多个要点 → 必须各有独立**固定标题**小节 + 占位
    aspects = extract_listed_aspects(description)
    if len(aspects) >= 2:
        missing_heading = [
            a
            for a in aspects
            if not _aspect_has_fixed_heading(a, compiled_l, aspects)
        ]
        if missing_heading:
            issues.append(
                "用户并列要求的要点缺少固定小节标题（栏目名须写成 ## 固定文字，"
                "内容放在标题下的占位里，禁止用「# [整段内容]」吞掉栏目名）："
                + "、".join(missing_heading[:6])
            )
        missing_own = [
            a for a in aspects if not _aspect_has_own_slot(a, compiled_l, aspects)
        ]
        if missing_own and not missing_heading:
            issues.append(
                "用户并列要求的要点未各自拆成独立小节/占位："
                + "、".join(missing_own[:6])
                + "（禁止合并成「A与B」一个标题）"
            )
        # 只有 1 个占位却要求多个方面 → 覆盖不足
        if len(fields) < min(len(aspects), 3) and len(aspects) >= 3:
            issues.append(
                f"用户列了 {len(aspects)} 个要点，但模板仅 {len(fields)} 个占位，"
                "请按要点拆成多个小节"
            )
        # 仍存在「A与B」合并标题，且 A、B 都是用户并列要点 → 明确报错
        for m in re.finditer(r"(?m)^#{1,3}\s+(.+)$", compiled_l):
            clean = _strip_heading_number(m.group(1))
            if not re.search(r"[与和及]", clean):
                continue
            hit = [a for a in aspects if a in clean]
            if len(hit) >= 2:
                issues.append(
                    f"标题 {m.group(1).strip()!r} 把并列要点合并了，"
                    "请拆成各自独立的 ## 小节"
                )
                break
        # 字数约束不得出现在固定文字行
        outer = re.sub(r"\[[^\[\]]*\]", " ", compiled_l)
        if re.search(r"(?:约\s*)?\d+\s*[-–—~～]?\s*\d*\s*字", outer):
            issues.append(
                "字数约束写进了固定文字，会泄漏到正文；请只写在占位说明内"
            )
        # 段落级字数禁止写成「全文合计」
        try:
            from tools.template_eval import is_section_scoped_char_budget
        except Exception:  # noqa: BLE001
            is_section_scoped_char_budget = None  # type: ignore[assignment]
        if is_section_scoped_char_budget and is_section_scoped_char_budget(
            description or ""
        ):
            if re.search(r"全文合计约\s*\d+", compiled_l):
                issues.append(
                    "用户字数约束只针对某一段/栏目，请写成「本段约N字」，"
                    "不要写成「全文合计约N字」"
                )

    # 「不遗漏关键…」是质量要求，不应单独开栏导致超字数
    if re.search(r"不遗漏关键|勿漏关键|不要遗漏关键", description or ""):
        if re.search(r"(?m)^##\s*关键", compiled_l):
            issues.append(
                "「不遗漏关键要点」无需单独开「## 关键…」节，请并入流程/脉络并控制总字数"
            )

    # 表格占位行必须含 [方括号] 占位符（LLM 偶发把占位写成（中文括号）→ 填充系统识别不到 → 表格不填）
    # 只检查「分隔行之后的数据行」——表头行/分隔行本身不含占位符是正常的
    _sep_re = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
    missing_ph: list[str] = []
    prev_sep = False
    for ln in compiled_l.splitlines():
        if "|" in ln and _sep_re.match(ln):
            prev_sep = True
            continue
        if "|" in ln and prev_sep and not re.search(r"\[[^\[\]]+\]", ln):
            missing_ph.append(ln)
        prev_sep = False
    if missing_ph:
        issues.append(
            "表格占位行缺少 [方括号] 占位符："
            + "；".join(ln.strip() for ln in missing_ph[:3])
            + "——表格每个可变单元格必须写成 [占位说明]（如 [风险描述；约3行]），"
            "禁止用（中文括号）或留空单元格"
        )

    # 用户点名的结构应有对应痕迹（固定字或占位说明）
    flag_needles: dict[str, list[str]] = {
        "time": ["时间", "日期"],
        "people": ["参会", "人员", "人物", "出席"],
        "progress": ["进展", "进度"],
        "problem": ["问题", "风险", "阻塞"],
        "next": ["下一步", "待办", "行动", "后续"],
        "summary": ["总结", "概要", "摘要"],
        "decision": ["决策", "决议"],
        "table": ["|"],
        "json": ["{", "["],
        "title": ["# ", "标题", "主题"],
    }
    for flag, needles in flag_needles.items():
        if flag not in flags:
            continue
        if flag == "json":
            # 自然语言说 JSON 时编译成占位符骨架也可；不强制
            continue
        if not any(n in compiled_l for n in needles):
            issues.append(f"用户提到「{flag}」但模板中未见对应结构")

    # 用户未提及时禁止扩写
    for mention_pat, markers, label in _EXPANSION_GUARDS:
        if mention_pat.search(description or ""):
            continue
        # minimal / 短描述时更严；否则仅拦明显的二级标题扩写
        hit = [m for m in markers if m in compiled_l]
        if not hit:
            continue
        if cues["minimal"] or cues["no_extra"] or len((description or "").strip()) < 80:
            issues.append(f"用户未要求「{label}」，但模板出现了：{hit[0]!r}")
        elif any(m.startswith("##") for m in hit):
            issues.append(f"用户未要求「{label}」，但模板增加了章节：{hit[0]!r}")

    # 部分数量约束
    n = cues.get("section_count")
    if isinstance(n, int) and n > 0:
        h2 = len(re.findall(r"(?m)^##\s+\S", compiled_l))
        # 也统计「1. 2. 3.」类分段
        numbered = len(re.findall(r"(?m)^\s*(?:\d+[\.、]|[一二三四五六七八九十]+[、.])\s+\S", compiled_l))
        sections = max(h2, numbered)
        if sections > n + 1:
            issues.append(
                f"用户要求约 {n} 个部分，但模板出现了 {sections} 个分段/标题"
            )

    # 短描述却编出很长模板 → 过度发挥
    desc_len = len((description or "").strip())
    if desc_len and desc_len < 60 and len(compiled_l) > max(400, desc_len * 12):
        if cues["minimal"] or cues["section_count"]:
            issues.append("编译模板相对描述过长，可能添加了用户未要求的结构")

    return issues


COMPILE_SYSTEM_PROMPT_TEMPLATE = """你是模板编译器：把中文用户用自然语言描述的"输出格式要求"，精确编译成一个可编辑的占位符模板。
{ctx_block}

## 第一步：先解析用户意图（在脑中完成，不要输出）
动手编译前，把描述拆成四层，缺的层按中文表达习惯补全：
1. **结构**：用户要哪几个部分（标题 / 元信息行 / 段落 / 列表 / 表格），先后顺序
2. **位置与固定文字**：哪些文字原样保留（标题、括号、标签、分隔符），哪些位置是可变占位
3. **体裁参照**：用户说"类似 / 像 …一样"时，该体裁的常规形态是什么
4. **约束与偏好**：数量、字数、行数、风格（正式/简洁/突出重点）、排除项（"不要…"）

## 中文表达习惯（帮助理解省略与隐含结构）
- **句间承接**：中文口语常省略主语，一句接一句的隐含顺序 = 表述顺序
- **"XX 一行"** → 该部分占一行
- **"括号里写 XX"** → 括号是固定文字，括号内是占位
- **"然后 / 接着 / 最后"** → 结构顺序
- **"类似 / 像 …一样"** → 体裁参照，不新增用户没点的栏目
- **"不要 / 别加 / 不用 …"** → 明确排除
- **数量词**："几行 / 约 N 字 / 三条" → 约束，只进占位说明

## 忠实于用户描述（最重要）
1. 只保留用户点名的结构，不增不减；顺序与用户表述一致
2. **按用户描述给结构，不为段落/表格额外加栏目包装标题**：
   - 用户说「第一行是标题」→ 直接 `# [标题占位]`，不要「## 纪要标题：」包装
   - 用户说「纪要约200字」→ 直接 `[纪要正文占位，约200字]`（一段），不要「## 纪要」标题
   - 用户说「风险表约3行」→ 直接给表格（表头+分隔+占位行），不要「## 风险识别」标题
   - 只有当用户**明确用顿号/与/和/及列出多个并列栏目**（如「概括背景、对象、目的」）
     时，才给每个栏目一个 `## 栏目名` 固定标题：
     ```text
     ## 栏目名
     [该栏正文占位说明…]
     ```
   - `## 栏目名` 是**固定文字**（用户打开文档能看见的标题），禁止省略
   - 正文只写在标题下方的 `[占位]` 里
   - **禁止**把栏目正文写进一级标题占位：`# [一大段背景…]`（这会导致「没有标题、只有内容」）
   - **禁止**合并：`## A与B` + 一个占位；必须 `## A` / `## B` 各一节
3. 用户说"类似 XX" → 对齐该体裁常规形态，仍以用户点名部分为准
4. 数量 / 字数 / 行数约束（**作用域必须分清**）：
   - **段落/栏目级**（常见）：「第一段…200字左右」「纪要约200字」「摘要100字以内」
     → 只写进**对应那一节**的占位说明，用「本段约200字 / 本栏约200字」，
     **禁止**写成「全文合计约200字」（会误伤其它段与表格）
   - **全文级**（少见）：「全文约200字」「整篇200-300字」或句首总起「约200字，概括…」
     且未点名某一段 → 才用「全文合计约200字」，仍只写进占位说明、不写固定文字行
   - "三行" / "三条" / "三行左右" / "约3行" + "以表格展示"
     → **不要真的生成 3 行占位模板**，表格里只保留 1 行数据模板，
     并把行数写进该表第一列占位说明，如 `[风险描述；约3行]`
     或 `[任务；约3行]`；表格段不要塞全文字数
   - "简洁 / 粗略" → 写进占位说明，不删栏目
   - **绝对禁止**把字数写成单独一行固定文字（否则会出现在用户正文里）

## 占位符写法
- [短中文说明]：填什么 + 从原文哪类信息提炼 + 信息不足怎么办
- **说明要简短口语、面向非程序员**（如「会议纪要，约200字」「任务内容」「负责人」），
  不要写「从原文提炼…通顺完整句…」这类长技术句——占位说明会直接显示为
  用户在预览框里看到的灰字提示，必须像人话
- 禁止在占位里写具体答案示范（如「如：小明」）
- 默认空值：用户指定则用用户的，否则「未提及」
- 不要单独增加一个「字数说明」占位或固定行

## 表格行数
- 表格永远只写一行占位数据行，作为生成时的行模板。
- 用户说「三行左右 / 约3行 / 三条左右」时，必须把约束写入该表第一列占位。
- **表格占位行的每个可变单元格必须用 [方括号] 占位符**，
  如 `| [风险描述；约3行] | [影响程度] | [应对措施] |`；
  禁止用（中文括号）包裹占位（如 `（约3行，生成时填写）`），
  禁止把可变单元格写成空单元格或固定文字——否则填充系统识别不到，表格会原样漏出。
  `| [风险描述；约3行] | [影响] | [应对] |`
- 禁止为了表达「3行」而复制 3 条占位数据行；否则后续会被当成多个独立表格模板。

## 描述模糊时的处理
- 有歧义时按最自然的理解补全，并在占位说明标注「按理解」
- 拿不准时宁可少加结构，不要擅自补栏目
- 完全无法理解 → 只输出 __NEED_CLARIFICATION__

## 示例（仅演示写法，不是目标结构）

用户甲（全文级）："约200字，概括主题甲、主题乙"
```text
## 主题甲
[从原文提炼与本栏相关的信息；无则写「未提及」；全文合计约200字]

## 主题乙
[从原文提炼与本栏相关的信息；无则写「未提及」]
```

用户乙（段落级，注意不要写「全文合计」）：
"分三段输出。第一段是纪要内容，200字左右，第二段是待办事项，以表格展示，三行左右。第三段是风险提取，以表格展示，三行左右。"
```text
## 纪要内容
[从原文提炼会议核心讨论与结论，通顺完整句；本段约200字；无则写「未提及」]

## 待办事项
| 任务 | 负责人 | 截止时间 |
| --- | --- | --- |
| [任务；约3行] | [负责人；未提及则写「未提及」] | [截止时间；未提及则写「未提及」] |

## 风险提取
| 风险描述 | 影响程度 | 应对措施 |
| --- | --- | --- |
| [风险；约3行] | [影响；未提及则写「未提及」] | [应对；未提及则写「未提及」] |
```
错误：把「本段约200字」写成「全文合计约200字」，或把字数约束套到待办/风险表上。

只输出编译后的模板正文，不要解释；**禁止**用 Markdown 代码围栏（``` 或 ```text）包裹整段输出。
{revision}"""


def _build_compile_system(
    *,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
    revision_notes: str = "",
) -> str:
    ctx_lines = []
    if domain or line_name:
        ctx_lines.append(
            f"当前任务上下文：domain={domain or '未知'}，任务线={line_name or '未知'}。"
        )
    if schema_hint.strip():
        ctx_lines.append(
            f"可用的上游内容字段（占位说明对齐这些来源，勿编造其它栏目）：\n{schema_hint.strip()}"
        )
    ctx_block = ("\n".join(ctx_lines) + "\n\n") if ctx_lines else ""

    revision = ""
    if revision_notes.strip():
        revision = (
            "\n\n【上次编译未通过保真检查，请修正】\n"
            f"{revision_notes.strip()}\n"
            "删除用户未要求的栏目；补全用户点名结构；控制总字数提示。\n"
        )

    return COMPILE_SYSTEM_PROMPT_TEMPLATE.format(
        ctx_block=ctx_block, revision=revision
    )


def _compile_cache_key(
    text: str,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
) -> str:
    payload = "\n".join(
        [
            _COMPILE_CACHE_VERSION,
            domain or "",
            line_name or "",
            schema_hint or "",
            text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_document_char_budget_line(source: str, compiled: str) -> str:
    """若自然语言源有**全文级**字数而编译结果丢失，把全文预算写入首个占位说明。

    段落级（「第一段…200字」「纪要约200字」）不注入「全文合计」，避免误伤其它段。
    不写进固定文字行，避免 assemble 后用户正文出现「全文约××字」。
    """
    try:
        from tools.template_eval import (
            is_section_scoped_char_budget,
            parse_char_budget,
            parse_document_char_budget,
        )
    except Exception:  # noqa: BLE001
        return compiled

    src = source or ""
    body = compiled or ""

    # 段落级：确保对应节占位有「本段约N字」，绝不写「全文合计」
    if is_section_scoped_char_budget(src) and not re.search(
        r"全文(?:合计)?|整篇|通篇", src
    ):
        b = parse_char_budget(src)
        if not b.get("hi"):
            return compiled
        hi = int(b["hi"])
        lo = b.get("lo")
        section_hint = (
            f"本段约{int(lo)}-{hi}字" if lo and int(lo) != hi else f"本段约{hi}字"
        )
        # 已有本段/本栏字数则不动；若误写成全文合计则改回本段
        if re.search(r"本段约\s*\d+|本栏约\s*\d+", body):
            body2 = re.sub(
                r"全文合计约\s*(\d+(?:\s*[-–—~～至到]\s*\d+)?)\s*字",
                lambda m: f"本段约{m.group(1).replace('至', '-').replace('到', '-')}字",
                body,
            )
            return body2
        if re.search(r"全文合计约\s*\d+", body):
            return re.sub(
                r"全文合计约\s*(\d+(?:\s*[-–—~～至到]\s*\d+)?)\s*字",
                lambda m: f"本段约{m.group(1).replace('至', '-').replace('到', '-')}字",
                body,
            )
        # 注入第一个正文占位（跳过表格行内占位：所在行含 |）
        for m in re.finditer(r"\[[^\[\]]+\]", body):
            line_start = body.rfind("\n", 0, m.start()) + 1
            line_end = body.find("\n", m.end())
            if line_end < 0:
                line_end = len(body)
            line = body[line_start:line_end]
            if "|" in line:
                continue
            inner = m.group(0)[1:-1].strip()
            if re.search(r"本段约|本栏约|全文合计", inner):
                return body
            new_ph = f"[{inner}；{section_hint}]"
            return body[: m.start()] + new_ph + body[m.end() :]
        return compiled

    # 全文级：仅在源描述确为全文预算时注入
    src_b = parse_document_char_budget(src)
    if not src_b.get("hi"):
        return compiled
    dst_b = parse_document_char_budget(body)
    if dst_b.get("hi"):
        return compiled
    lo, hi = src_b.get("lo"), src_b.get("hi")
    if lo and hi:
        hint = f"全文合计约{int(lo)}-{int(hi)}字"
    else:
        hint = f"全文合计约{int(hi)}字"
    if hint in body or re.search(r"全文(?:合计)?约?\s*\d+", body):
        return compiled
    m = re.search(r"\[[^\[\]]+\]", body)
    if not m:
        return compiled
    inner = m.group(0)[1:-1].strip()
    if "全文" in inner:
        return compiled
    new_ph = f"[{inner}；{hint}]"
    return body[: m.start()] + new_ph + body[m.end() :]


def _extract_table_row_limits(source: str) -> dict[str, int]:
    """从自然语言描述中抽取表格主题的行数约束。"""
    limits: dict[str, int] = {}
    if not source:
        return limits
    chunks = re.split(r"[。！？!?；;\n]+", source)
    for chunk in chunks:
        text = chunk.strip()
        if not text:
            continue
        limit = _table_row_limit_from_text(text)
        if not limit:
            continue
        if re.search(r"风险|阻塞|问题", text):
            limits["risk"] = limit
        if re.search(r"待办|行动|任务|下一步|后续", text):
            limits["action"] = limit
        if "表" in text or "表格" in text:
            limits.setdefault("any", limit)
    return limits


def _inject_row_limit_into_table_row(row: str, limit: int) -> str:
    """把「约N行」写进表格首个占位说明；已有行数说明则不重复写。"""
    if not row or "[" not in row:
        return row
    if _table_row_limit_from_text(row):
        return row

    def repl(m: re.Match[str]) -> str:
        inner = m.group(1).strip()
        if _table_row_limit_from_text(inner):
            return m.group(0)
        return f"[{inner}；约{limit}行]"

    return _PLACEHOLDER_RE.sub(repl, row, count=1)


def _ensure_table_row_limits(source: str, compiled: str) -> str:
    """自然语言编译后补强表格行数约束，并折叠重复模板行。"""
    limits = _extract_table_row_limits(source)
    if not limits or not compiled:
        return compiled
    lines = compiled.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_table_data_row(line):
            topic = _table_topic_from_context(lines, i)
            limit = limits.get(topic) or limits.get("any")
            row = _inject_row_limit_into_table_row(line, limit) if limit else line
            out.append(row)
            # LLM 有时会按「3行」直接复制 3 行占位模板；这里只保留一行模板。
            i += 1
            while i < len(lines) and _is_table_data_row(lines[i]):
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


async def maybe_compile_natural_template(
    text: str,
    *,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
    client: Any = None,
) -> str:
    """自然语言描述 → 占位符模板（带保真检查与最多 2 次编译）。

    - 开关关闭或非 natural：原样返回
    - 编译成功且通过保真检查：返回编译结果（按 domain/line 缓存）
    - 失败：返回原文并 warning（调用方按旧路径继续，不阻塞）
    """
    if not is_router_enabled():
        return text
    if not text or not text.strip():
        return text
    if detect_template_kind(text) != "natural":
        return text

    key = _compile_cache_key(text, domain, line_name, schema_hint)
    if key in _COMPILE_CACHE:
        return _COMPILE_CACHE[key]
    if _COMPILE_FAIL_COUNTS.get(key, 0) >= _COMPILE_FAIL_SKIP_THRESHOLD:
        return text

    try:
        if client is None:
            from llm_client import LLMClient  # 延迟 import，避免顶层耦合

            client = LLMClient()
        revision = ""
        last_compiled = ""
        for attempt in range(2):
            system = _build_compile_system(
                domain=domain,
                line_name=line_name,
                schema_hint=schema_hint,
                revision_notes=revision,
            )
            compiled = (
                await _client_text(
                    client,
                    system,
                    text,
                    temperature=0.0,
                    use_cache=(attempt == 0 and not revision),
                    label="template/compile",
                )
            ).strip()
            last_compiled = compiled
            if not compiled or compiled == "__NEED_CLARIFICATION__":
                revision = "输出无法使用：请生成含 [占位符] 的模板，不要解释。"
                continue
            # 去掉模型误包的代码围栏（```text / ```markdown 等）
            compiled = strip_outer_markdown_fence(compiled)
            if detect_template_kind(compiled) != "placeholder":
                revision = "结果缺少 [占位符]：请把可变部分写成 [说明] 形式。"
                continue
            fidelity = check_compile_fidelity(text, compiled)
            if fidelity:
                revision = "\n".join(f"- {x}" for x in fidelity)
                logger.info(
                    "自然语言模板保真未通过（attempt=%s）：%s",
                    attempt + 1,
                    "；".join(fidelity),
                )
                continue
            compiled = _ensure_document_char_budget_line(text, compiled)
            compiled = _ensure_table_row_limits(text, compiled)
            _COMPILE_CACHE[key] = compiled
            _COMPILE_FAIL_COUNTS.pop(key, None)
            return compiled

        # 两次都未完美：若最后一稿至少是 placeholder，降级采用并打 warning
        if last_compiled and detect_template_kind(last_compiled) == "placeholder":
            soft = check_compile_fidelity(text, last_compiled)
            last_compiled = _ensure_document_char_budget_line(text, last_compiled)
            last_compiled = _ensure_table_row_limits(text, last_compiled)
            logger.warning(
                "自然语言模板保真未完全通过，仍采用编译结果（issues=%s）",
                "；".join(soft) if soft else "n/a",
            )
            _COMPILE_CACHE[key] = last_compiled
            return last_compiled

        _COMPILE_FAIL_COUNTS[key] = _COMPILE_FAIL_COUNTS.get(key, 0) + 1
        logger.warning("自然语言模板编译未能理解，已按原样处理（原逻辑）")
        return text
    except Exception:  # noqa: BLE001 - 编译失败不阻塞运行
        _COMPILE_FAIL_COUNTS[key] = _COMPILE_FAIL_COUNTS.get(key, 0) + 1
        logger.warning("自然语言模板编译失败，已按原样处理（原逻辑）", exc_info=True)
        return text


async def modify_template(
    template: str,
    instruction: str,
    *,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
) -> str:
    """自然语言增量修改占位模板：基于当前模板 + 修改意见 → 新模板。

    - 输入不是占位模板或修改意见为空：原样返回
    - 修改成功：返回新占位模板（带保真检查 + 最多 2 次重试）
    - 失败：返回原模板（不阻塞，调用方保留当前预览）
    """
    if not instruction or not instruction.strip():
        return template
    if detect_template_kind(template or "") != "placeholder":
        return template
    try:
        from llm_client import LLMClient  # 延迟 import

        client = LLMClient()
        ctx = ""
        if domain or line_name:
            ctx += f"当前任务上下文：domain={domain or '未知'}，任务线={line_name or '未知'}。\n"
        if schema_hint.strip():
            ctx += f"可用的上游内容字段（占位说明对齐这些来源，勿编造其它栏目）：\n{schema_hint.strip()}\n"
        user = _MODIFY_SYSTEM.format(template=template, instruction=instruction)
        if ctx:
            user = ctx + "\n" + user
        revision = ""
        last = ""
        for attempt in range(2):
            compiled = (
                await _client_text(
                    client,
                    _build_compile_system(
                        domain=domain,
                        line_name=line_name,
                        schema_hint=schema_hint,
                        revision_notes=revision,
                    ),
                    user + (f"\n\n【上次修改未通过保真检查，请修正】\n{revision}" if revision else ""),
                    temperature=0.0,
                    label="template/compile",
                )
            ).strip()
            last = compiled
            compiled = strip_outer_markdown_fence(compiled)
            if detect_template_kind(compiled) != "placeholder":
                revision = "结果缺少 [占位符]：请保留占位符模板形式。"
                continue
            fidelity = check_compile_fidelity(instruction, compiled)
            if fidelity:
                revision = "\n".join(f"- {x}" for x in fidelity)
                continue
            return compiled
        if detect_template_kind(last) == "placeholder":
            logger.warning("模板增量修改保真未完全通过，仍采用（issues=%s）",
                           "；".join(check_compile_fidelity(instruction, last)) or "n/a")
            return strip_outer_markdown_fence(last)
        return template
    except Exception:  # noqa: BLE001 - 修改失败不阻塞
        logger.warning("模板增量修改失败，保留当前模板", exc_info=True)
        return template


def merge_preview_fill(old_preview: dict[str, Any], new_template: str) -> dict[str, Any]:
    """增量修改后保留已填内容：按段类型+标题/提示对齐，结构未变段落回填 value。

    - 段落（field）：hint 相同或标题相邻相同 → 保留旧 value
    - 表格（table）：标题相同且列数相同 → 保留旧 rows；列数变化 → 丢弃（需重填）
    - 新增段落/表格：空
    """
    if not old_preview or not new_template:
        return template_to_preview(new_template or "")
    old_sections = (old_preview or {}).get("sections") or []
    new_preview = template_to_preview(new_template)
    new_sections = new_preview.get("sections") or []

    old_fields = [s for s in old_sections if s.get("type") == "field"]
    old_tables = [s for s in old_sections if s.get("type") == "table"]

    field_i = 0
    table_i = 0
    for sec in new_sections:
        stype = sec.get("type")
        if stype == "field" and field_i < len(old_fields):
            old = old_fields[field_i]
            # 结构未变判定：提示语相同（归一化后）
            if _hint_clean(str(old.get("hint") or "")) == _hint_clean(
                str(sec.get("hint") or "")
            ):
                sec["value"] = old.get("value") or ""
            field_i += 1
        elif stype == "table" and table_i < len(old_tables):
            old = old_tables[table_i]
            old_headers = [str(h) for h in (old.get("headers") or [])]
            new_headers = [str(h) for h in (sec.get("headers") or [])]
            if old_headers == new_headers:
                sec["rows"] = old.get("rows") or sec.get("rows") or []
            table_i += 1
    return new_preview


