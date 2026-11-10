from __future__ import annotations

from collections.abc import AsyncIterator

import re
from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt

from ..prompts import MINDMAP_RENDER_PROMPT, MINDMAP_RENDER_TEMPLATE_PROMPT


def normalize_mindmap_outline(text: str) -> str:
    r"""确定性思维导图大纲拓扑门禁与清洗器。

    1. 去除 Markdown 代码块包裹（```markdown / ```）；
    2. 剔除 Markdown 表格语法行（包含 |---| 或首尾以 | 闭合的表格行）；
    3. 深度拓扑降级：将 5 级及以上标题（^#{5,}\s+(.*)）平铺降级为 4 级叶子 `    - \1`；
    4. 超长节点截断：叶子行内容若超过 35 字，智能截断至 32 字 + '...';
    """
    if not text or not text.strip():
        return text or ""
    lines = text.strip().splitlines()
    cleaned_lines: list[str] = []
    in_code_block = False
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_code_block = not in_code_block
            continue
        # 过滤表格行
        if s.startswith("|") and s.endswith("|"):
            continue
        if re.match(r"^\|?[\s\-:]+\|[\s\-:|]+$", s):
            continue
        # 5 级及以上标题降级为 4 级列表项
        m_deep = re.match(r"^#{5,}\s*(.*)$", s)
        if m_deep:
            heading_text = m_deep.group(1).strip()
            line = f"    - {heading_text}"
            s = line.strip()
        # 超长叶子截断
        m_bullet = re.match(r"^(\s*[-*•]\s+)(.*)$", line)
        if m_bullet:
            prefix = m_bullet.group(1)
            content = m_bullet.group(2).strip()
            if len(content) > 35:
                content = content[:32] + "..."
            line = f"{prefix}{content}"
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


class MindmapRender:
    """Render the approved 思维导图 result."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client

    @staticmethod
    def render_draft(state: dict) -> str:
        """把已批准的思维导图草稿纯 Python 确定性组装为规范 Markdown 大纲（零 LLM 调用）。"""
        draft = (state.get("lines") or {}).get("mindmap", {}).get("draft") or {}
        outline = str(draft.get("outline") or "").strip()
        if outline:
            return normalize_mindmap_outline(outline)
        title = str(draft.get("title") or "").strip() or "思维导图"
        return f"# {title}\n\n- 暂无思维导图大纲"

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        return build_render_prompt(
            context,
            template,
            MINDMAP_RENDER_PROMPT,
            MINDMAP_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, approved_context: str, template: str = "") -> str:
        """若被外部显式调用，直接通过确定性物理清洗器清洗输出，零 LLM 开销。"""
        return normalize_mindmap_outline(approved_context)

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        cleaned = normalize_mindmap_outline(approved_context)
        yield cleaned

