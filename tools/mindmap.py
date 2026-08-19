"""mindmap.py —— 思维导图 HTML 生成（markmap-cli 封装，无痛降级）。

把 Markdown 大纲（mindmap 任务线的 outline 字段）渲染为交互式
HTML 思维导图（markmap）：

- 依赖：Node + npx（``npx --yes markmap-cli`` 首次自动下载，无需全局安装）
- 产物：``--offline`` 单文件 HTML，所有 JS/CSS 内联，可离线打开/分享
- 设计约束（沿用 tools/template_router/ 的无痛惯例）：
  - ``npx`` 不可用 / 网络失败 / 超时 → 一律返回 ``None``，**不影响主流程**
  - 纯函数，不 import 任何任务线 / domain
  - 临时文件放输出目录，且自动处理 WSL(linux) 调 Windows node 的路径差异
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# markmap-cli 版本固定，避免 npx 解析漂移
_MARKMAP_CLI_VERSION = "0.18.12"
_RENDER_TIMEOUT_SECONDS = 120


def markmap_available() -> bool:
    """npx 是否可用（与 render_mindmap_html 的启动入口一致）。"""
    return shutil.which("npx") is not None


def mindmap_png_available() -> bool:
    """Playwright（PNG 截图依赖）是否可导入。"""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _npx_command(npx: str, args: list[str]) -> list[str]:
    """组装实际启动 npx 的命令。

    Windows 上 npx 通常是 ``npx.cmd``（CreateProcess 无法直接启动
    ``.cmd/.bat``），需经 ``cmd.exe /c``（shell=True）执行；
    Linux/macOS 上直接调用 npx 可执行文件。
    """
    if npx.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", subprocess.list2cmdline([npx, *args])]
    return [npx, *args]


def _native_path(path: Path) -> str:
    """把路径转成实际执行 node 的进程能访问的形式。

    仅当 Python 跑在 WSL（linux）而 npx 是 Windows 程序（如
    ``C:\\...\\npx.cmd``，WSL 内通过 PATH 可见）时，把 ``/mnt/d/x``
    转成 ``D:\\x``；Windows 原生环境原样返回。
    """
    s = str(path)
    if sys.platform.startswith("linux"):
        m = re.match(r"^/mnt/([a-zA-Z])/(.+)$", s)
        if m:
            # 反斜杠移出 f-string 表达式，兼容 Python < 3.12
            drive = m.group(1).upper()
            rest = m.group(2).replace("/", "\\")
            return f"{drive}:\\{rest}"
    return s


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_HTML_TABLE_RE = re.compile(
    r"<table\b[\s\S]*?</table>",
    re.IGNORECASE,
)


def _is_table_row(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    # 至少两段竖线才视为表格行（避免普通句子里的单个 |）
    return s.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEP_RE.match(line.strip()))


def _split_table_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _short_node(text: str, max_len: int = 28) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    # 去掉状态图标等噪音
    text = text.replace("✅", "").replace("🟡", "").replace("🔴", "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _table_block_to_bullets(table_lines: list[str]) -> list[str]:
    """把 Markdown 表转为短分支叶子；不保留表头/分隔行。"""
    rows: list[list[str]] = []
    for line in table_lines:
        if _is_table_separator(line):
            continue
        cells = _split_table_cells(line)
        if not cells or all(not c for c in cells):
            continue
        rows.append(cells)
    if not rows:
        return []

    # 首行若像表头（含「状态/负责人/事项」等），跳过
    header_hints = (
        "模块",
        "事项",
        "状态",
        "负责人",
        "责任",
        "进度",
        "风险",
        "等级",
        "时间",
        "计划",
        "交付",
        "标准",
        "依赖",
        "当前",
        "下一",
        "瓶颈",
        "范围",
        "应对",
        "待办",
        "截止",
    )
    start = 0
    if rows and any(h in "".join(rows[0]) for h in header_hints):
        start = 1

    bullets: list[str] = []
    seen: set[str] = set()
    for cells in rows[start:]:
        # 优先第一列作分支名；第二列有实质内容时作补充（截断）
        primary = _short_node(cells[0] if cells else "")
        if not primary:
            continue
        secondary = ""
        if len(cells) > 1:
            # 跳过纯状态词单独展示过长进展
            for c in cells[1:]:
                c2 = c.strip()
                if not c2:
                    continue
                if c2 in {"已完成", "进行中", "待开始", "未明确", "高", "中", "低"}:
                    secondary = c2
                    break
                secondary = _short_node(c2, 18)
                break
        label = primary if not secondary else f"{primary}：{secondary}"
        label = _short_node(label, 36)
        if label in seen:
            continue
        seen.add(label)
        bullets.append(f"- {label}")
    return bullets


def sanitize_mindmap_outline(outline: str) -> str:
    """清理思维导图大纲：去掉表格/HTML 表，只保留标题层级与短分支。

    markmap 会把 Markdown 表格渲染成嵌在节点上的整表，破坏「分支展示分支」
    的可读性。本函数在渲染前做硬约束：
    - ``|...|`` 表格块 → 数据行改为 ``- 短句`` 叶子
    - ``<table>...</table>`` 直接删除
    - 过长节点截断
    """
    text = (outline or "").strip()
    if not text:
        return ""

    text = _HTML_TABLE_RE.sub("", text)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _is_table_row(line):
            block = [line]
            i += 1
            while i < n and (
                _is_table_row(lines[i])
                or _is_table_separator(lines[i])
                or not lines[i].strip()
            ):
                # 空行结束表格（若后面不再是表行）
                if not lines[i].strip():
                    # 前瞻：空行后仍是表则吞掉空行，否则结束
                    j = i + 1
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and _is_table_row(lines[j]):
                        i = j
                        continue
                    break
                block.append(lines[i])
                i += 1
            bullets = _table_block_to_bullets(block)
            out.extend(bullets if bullets else [])
            continue

        stripped = line.strip()
        # 禁止残留 HTML 标签碎片
        if stripped.lower().startswith(("<tr", "<td", "<th", "<thead", "<tbody", "</")):
            i += 1
            continue

        # 标题/列表保留；普通长行截断为短节点
        if stripped.startswith("#"):
            # 标题本身也不宜过长
            m = re.match(r"^(#{1,4}\s+)(.*)$", stripped)
            if m:
                out.append(f"{m.group(1)}{_short_node(m.group(2), 40)}")
            else:
                out.append(stripped)
        elif stripped.startswith(("- ", "* ", "+ ")):
            mark = stripped[:2]
            body = stripped[2:]
            out.append(f"{mark}{_short_node(body, 36)}")
        elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
            m = re.match(r"^(\d+\.\s+)(.*)$", stripped)
            if m:
                out.append(f"- {_short_node(m.group(2), 36)}")
            else:
                out.append(f"- {_short_node(stripped, 36)}")
        elif not stripped:
            # 压缩多余空行
            if out and out[-1] != "":
                out.append("")
        else:
            # 游离段落 → 短叶子，避免整段贴在节点上
            out.append(f"- {_short_node(stripped, 36)}")
        i += 1

    # 收尾空行
    while out and out[-1] == "":
        out.pop()
    cleaned = "\n".join(out).strip()
    # 确保至少有一个一级标题，markmap 才稳定
    if cleaned and not re.search(r"(?m)^#\s+\S", cleaned):
        cleaned = f"# 思维导图\n\n{cleaned}"
    # 同前缀叶子上提为子分支（如多条「技术组：…」→ ### 技术组 + 叶子）
    cleaned = factor_common_prefixes(cleaned)
    return cleaned


# ── 公共前缀上提为子分支 ─────────────────────────────────────

# 叶子「类别：具体内容」；类别宜短，避免把整句当前缀
_PREFIX_SPLIT_RE = re.compile(r"^(.{1,12}?)[：:](.+)$")
# 次选：短类别 + 破折号/间隔（少见）
_PREFIX_DASH_RE = re.compile(r"^(.{2,10}?)[-–—]\s*(.+)$")


@dataclass
class _MMNode:
    kind: str  # "heading" | "bullet"
    level: int  # heading 1-4；bullet 继承父级
    text: str
    children: list["_MMNode"] = field(default_factory=list)


def _split_leaf_prefix(text: str) -> tuple[str | None, str | None]:
    """把叶子拆成 (公共前缀, 剩余)。无法拆则 (None, None)。"""
    text = (text or "").strip()
    if not text:
        return None, None
    m = _PREFIX_SPLIT_RE.match(text)
    if m:
        pref, rest = m.group(1).strip(), m.group(2).strip()
        if pref and rest and not re.search(r"[，。；;]", pref):
            return pref, rest
    m = _PREFIX_DASH_RE.match(text)
    if m:
        pref, rest = m.group(1).strip(), m.group(2).strip()
        # 破折号更易误伤，前缀需像专名/部门（含中文或短词）
        if pref and rest and re.search(r"[\u4e00-\u9fff]", pref):
            return pref, rest
    return None, None


def _parse_outline_tree(outline: str) -> _MMNode:
    root = _MMNode("heading", 0, "", [])
    stack: list[_MMNode] = [root]
    for raw in (outline or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if not m:
                continue
            level = min(len(m.group(1)), 4)
            text = m.group(2).strip()
            node = _MMNode("heading", level, text, [])
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            stack[-1].children.append(node)
            stack.append(node)
            continue
        if line.startswith(("- ", "* ", "+ ")):
            body = line[2:].strip()
            parent = stack[-1]
            parent.children.append(_MMNode("bullet", parent.level, body, []))
            continue
        # 游离行挂到当前节点
        parent = stack[-1]
        parent.children.append(_MMNode("bullet", parent.level, line, []))
    return root


def _factor_bullet_run(
    bullets: list[_MMNode], parent_level: int
) -> list[_MMNode]:
    """同一父节点下，≥2 条共享「前缀：」的叶子 → 提升为子标题。"""
    if len(bullets) < 2:
        return list(bullets)

    # 按首次出现顺序记录前缀；无前缀的按原序穿插
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    sequence: list[tuple[str, str]] = []  # ("g", pref) | ("p", text)

    for b in bullets:
        pref, rest = _split_leaf_prefix(b.text)
        if pref and rest:
            if pref not in groups:
                groups[pref] = []
                sequence.append(("g", pref))
            groups[pref].append(rest)
        else:
            sequence.append(("p", b.text))

    # 仅出现 1 次的前缀不提升，还原为「前缀：内容」
    promote = {p for p, items in groups.items() if len(items) >= 2}
    if not promote:
        return list(bullets)

    # Markdown/markmap 约定：标题后的 - 叶子会挂在该标题下。
    # 因此必须先输出「仍挂在父级的叶子」，再输出上提后的 ### 子分支，
    # 否则无前缀叶子 / 仅 1 条的「类别：」会被错误吞进上一个 ###。
    plain_out: list[_MMNode] = []
    branch_out: list[_MMNode] = []
    emitted: set[str] = set()
    for kind, val in sequence:
        if kind == "p":
            plain_out.append(_MMNode("bullet", parent_level, val, []))
            continue
        pref = val
        items = groups[pref]
        if pref in emitted:
            continue
        emitted.add(pref)
        if pref not in promote or parent_level >= 4:
            for rest in items:
                plain_out.append(
                    _MMNode("bullet", parent_level, f"{pref}：{rest}", [])
                )
            continue
        # root(level=0) 下直接生成 ##，避免再造一个 #
        if parent_level <= 0:
            child_level = 2
        else:
            child_level = min(parent_level + 1, 4)
        branch = _MMNode("heading", child_level, _short_node(pref, 20), [])
        for rest in items:
            branch.children.append(
                _MMNode("bullet", child_level, _short_node(rest, 36), [])
            )
        branch_out.append(branch)
    return plain_out + branch_out


def _factor_tree(node: _MMNode) -> None:
    if not node.children:
        return
    new_children: list[_MMNode] = []
    i = 0
    kids = node.children
    while i < len(kids):
        ch = kids[i]
        if ch.kind == "heading":
            _factor_tree(ch)
            new_children.append(ch)
            i += 1
            continue
        # 连续 bullet 段
        j = i
        while j < len(kids) and kids[j].kind == "bullet":
            j += 1
        run = kids[i:j]
        new_children.extend(_factor_bullet_run(run, parent_level=node.level))
        i = j
    node.children = new_children
    # 提升后的子标题内部若还有可提升结构，再扫一层
    for ch in node.children:
        if ch.kind == "heading":
            _factor_tree(ch)


def _serialize_outline_tree(root: _MMNode) -> str:
    lines: list[str] = []

    def walk(n: _MMNode) -> None:
        if n.kind == "heading" and n.level > 0:
            lines.append(f"{'#' * n.level} {_short_node(n.text, 40)}")
        for ch in n.children:
            if ch.kind == "bullet":
                lines.append(f"- {_short_node(ch.text, 36)}")
            else:
                walk(ch)
        # 主分支之间空一行，markmap 更清晰
        if n.kind == "heading" and n.level == 2 and lines and lines[-1] != "":
            lines.append("")

    for ch in root.children:
        walk(ch)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def factor_common_prefixes(outline: str) -> str:
    """将同级叶子中重复的「类别：内容」上提为子分支。

    例：
        ## 整改项
        - 技术组：A
        - 技术组：B
        - 现场安装：C
    →
        ## 整改项
        ### 技术组
        - A
        - B
        ### 现场安装
        - C
    """
    text = (outline or "").strip()
    if not text:
        return ""
    root = _parse_outline_tree(text)
    _factor_tree(root)
    return _serialize_outline_tree(root)


def render_mindmap_html(
    outline: str,
    out_dir: Path | str,
    filename: str = "meeting_mindmap.html",
) -> Path | None:
    """把 Markdown 大纲渲染为离线 HTML 思维导图文件。

    Args:
        outline: markmap 输入（# 根节点 + ##/### 分支 + 列表项）。
        out_dir: 输出目录（不存在则创建）。
        filename: 输出文件名（默认 meeting_mindmap.html）。

    Returns:
        生成的 HTML 文件路径；任何失败返回 ``None``（不抛异常）。
    """
    outline = sanitize_mindmap_outline(outline or "")
    if not outline:
        logger.warning("思维导图大纲为空，跳过 HTML 生成")
        return None
    out_dir = Path(out_dir)
    md_path: Path | None = None
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename

        npx = shutil.which("npx")
        if not npx:
            logger.warning(
                "未检测到 npx/node，无法生成思维导图 HTML（可安装 Node.js 后重试）"
            )
            return None

        # 临时 md 放输出目录（路径对 node 可见；WSL 场景经 _native_path 转换）
        md_path = out_dir / f"._{filename}.md"
        md_path.write_text(outline, encoding="utf-8")

        cmd = _npx_command(
            npx,
            [
                "--yes",
                f"markmap-cli@{_MARKMAP_CLI_VERSION}",
                _native_path(md_path),
                "-o",
                _native_path(out_path),
                "--offline",
                "--no-open",
            ],
        )
        # Windows 经 cmd.exe /c 启动 .cmd 时需 shell=True；其余平台直接执行
        use_shell = npx.lower().endswith((".cmd", ".bat"))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_RENDER_TIMEOUT_SECONDS,
            check=False,
            shell=use_shell,
        )
        if result.returncode != 0:
            logger.warning(
                "markmap-cli 生成失败（rc=%s）：%s",
                result.returncode,
                (result.stderr or result.stdout or "").strip()[-500:],
            )
            return None
        if not out_path.exists():
            logger.warning("markmap-cli 未产出文件：%s", out_path)
            return None
        return out_path
    except subprocess.TimeoutExpired:
        logger.warning("markmap-cli 生成超时（>%ss），已放弃", _RENDER_TIMEOUT_SECONDS)
        return None
    except Exception:  # noqa: BLE001 - 生成失败不影响主流程
        logger.warning("思维导图 HTML 生成异常，已跳过", exc_info=True)
        return None
    finally:
        if md_path is not None:
            try:
                md_path.unlink(missing_ok=True)
            except OSError:
                pass


def _png_pixel_stats(path: Path, sample_every: int = 4) -> tuple[int, float]:
    """解码 PNG，返回 (采样不同颜色数, 非近白/近黑像素占比)。

    用于截图质量自检：
    - 颜色数过少 → 纯色图
    - 非背景像素过少 → 几乎全白/全黑的"假成功"空白图
      （入场动画未结束时常见：整图白底仅零星描边色）
    """
    import struct
    import zlib

    with path.open("rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0.0
    pos = 8
    idat = b""
    width = height = bit_depth = color_type = 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(
                ">IIBB", data[pos + 8 : pos + 18]
            )
        elif chunk_type == b"IDAT":
            idat += data[pos + 8 : pos + 8 + length]
        pos += 12 + length
    if bit_depth != 8 or not idat or width <= 0 or height <= 0:
        return 0, 0.0
    bpp = 4 if color_type == 6 else (3 if color_type == 2 else 1)
    raw = zlib.decompress(idat)
    stride = width * bpp
    colors: set = set()
    sample_n = 0
    content_n = 0
    p = 0
    prev = bytearray(stride)
    for y in range(height):
        f = raw[p]
        p += 1
        line = bytearray(raw[p : p + stride])
        p += stride
        if f == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif f == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:  # Average
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:  # Paeth
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        if y % sample_every == 0:
            for i in range(0, stride, bpp * sample_every):
                pix = tuple(line[i : i + bpp])
                colors.add(pix)
                sample_n += 1
                # RGB 亮度：近白(>=250) / 近黑(<=5) 视为背景
                r = pix[0] if bpp >= 3 else pix[0]
                g = pix[1] if bpp >= 3 else pix[0]
                b = pix[2] if bpp >= 3 else pix[0]
                if not (min(r, g, b) >= 250 or max(r, g, b) <= 5):
                    content_n += 1
        prev = line
    ratio = (content_n / sample_n) if sample_n else 0.0
    return len(colors), ratio


async def render_mindmap_png(
    outline: str,
    out_dir: Path | str,
    filename: str = "meeting_mindmap.png",
    html_path: Path | str | None = None,
) -> Path | None:
    """把思维导图 HTML 截图导出为 PNG（Playwright Async API + Chromium）。

    Args:
        outline: markmap 输入（复用 render_mindmap_html 的入口）。
        out_dir: 输出目录（不存在则创建）。
        filename: PNG 文件名。
        html_path: 已生成的 HTML 文件（复用，省去重新跑 npx）；None 则临时生成。

    Returns:
        PNG 文件路径；任何失败（playwright 未装 / chromium 缺失 / 超时）
        返回 ``None``（不抛异常）。

    Note:
        本项目运行在 asyncio 事件循环内，必须用 Async API
        （``async_playwright``）；Sync API 会报
        "Sync API inside the asyncio loop" 错误。
    """
    outline = sanitize_mindmap_outline(outline or "")
    if not outline:
        logger.warning("思维导图大纲为空，跳过 PNG 生成")
        return None
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning(
            "未安装 playwright，跳过 PNG 导出（安装：pip install playwright "
            "&& playwright install chromium）"
        )
        return None

    out_dir = Path(out_dir)
    html: Path | None = None
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        png_path = out_dir / filename

        if html_path:
            html = Path(html_path).resolve()
        else:
            # 临时生成 HTML（不覆盖外部产物）
            html = render_mindmap_html(
                outline, out_dir, f"._{filename}.html"
            )
            if html is not None:
                html = html.resolve()
        if html is None or not html.exists():
            logger.warning("思维导图 HTML 源不存在，无法导出 PNG")
            return None

        uri = html.as_uri()
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                # 强制 light：系统深色模式下 markmap 会加 .markmap-dark（白字），
                # 再补白底会变成白底白字，PNG 看起来全空白。
                page = await browser.new_page(
                    viewport={"width": 1600, "height": 1200},
                    device_scale_factor=2,
                    color_scheme="light",
                )
                await page.goto(uri, wait_until="load", timeout=30_000)
                # 1) 等 markmap 实例 + SVG 节点挂载
                # 2) 再等 getBBox 足够大且连续稳定——markmap 入场有 ~500ms
                #    d3 过渡动画；节点 DOM 一出现就截图会得到纯白/残缺图。
                # 注意：不要在稳定前调用 mm.fit()，fit 会重启动画。
                await page.wait_for_function(
                    """() => {
                        const svg = document.querySelector('svg#mindmap');
                        if (!(window.mm && svg)) return false;
                        const g = svg.querySelector('g');
                        if (!(g && g.childElementCount > 0)) return false;
                        let bb;
                        try {
                            bb = svg.getBBox();
                        } catch (e) {
                            return false;
                        }
                        // 入场初期 bbox 往往宽高很小（常见 height~20）；
                        // 动画结束后至少应有基本可视面积（小导图也可能 <200）
                        if (bb.width < 80 || bb.height < 80) return false;
                        const key = [
                            bb.x.toFixed(1),
                            bb.y.toFixed(1),
                            bb.width.toFixed(1),
                            bb.height.toFixed(1),
                        ].join(',');
                        if (window.__mmBbKey === key) {
                            window.__mmBbHits = (window.__mmBbHits || 0) + 1;
                        } else {
                            window.__mmBbKey = key;
                            window.__mmBbHits = 0;
                        }
                        // polling 默认约  raf/短间隔；连续命中同一 bbox 视为动画结束
                        return window.__mmBbHits >= 8;
                    }""",
                    timeout=20_000,
                )
                try:
                    await page.evaluate("() => document.fonts.ready")
                except Exception:  # noqa: BLE001 - 字体 API 失败不阻断截图
                    pass
                # 按内容 bbox 设 viewBox 并裁白边；补白底避免透明背景。
                # 不再调用 mm.fit()：create 时已 fit，再次 fit 会重启动画导致空白图。
                await page.evaluate(
                    """() => {
                        const svg = document.querySelector('svg#mindmap');
                        if (!svg) return;
                        document.documentElement.classList.remove('markmap-dark');
                        document.documentElement.style.background = '#ffffff';
                        document.body.style.background = '#ffffff';
                        document.body.style.margin = '0';
                        document.body.style.padding = '0';
                        svg.style.background = '#ffffff';
                        const bb = svg.getBBox();
                        const pad = 48;
                        const x = bb.x - pad;
                        const y = bb.y - pad;
                        const w = Math.max(bb.width + pad * 2, 100);
                        const h = Math.max(bb.height + pad * 2, 100);
                        svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
                        svg.setAttribute('width', String(Math.ceil(w)));
                        svg.setAttribute('height', String(Math.ceil(h)));
                        svg.style.width = Math.ceil(w) + 'px';
                        svg.style.height = Math.ceil(h) + 'px';
                        svg.style.maxWidth = 'none';
                        svg.style.display = 'block';
                    }"""
                )
                await page.wait_for_timeout(150)
                await page.locator("svg#mindmap").screenshot(path=str(png_path))
            finally:
                await browser.close()
        if not png_path.exists():
            return None
        # 质量自检：纯色 / 几乎无内容像素 → 丢弃（避免 Gradio 展示空白 PNG）
        color_n, content_ratio = _png_pixel_stats(png_path)
        if color_n < 8 or content_ratio < 0.005:
            logger.warning(
                "思维导图 PNG 截图异常（colors=%s content_ratio=%.4f，"
                "疑似空白/纯色图），已放弃：%s",
                color_n,
                content_ratio,
                png_path,
            )
            try:
                png_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return png_path
    except Exception:  # noqa: BLE001 - 截图失败不影响主流程
        logger.warning("思维导图 PNG 生成异常，已跳过", exc_info=True)
        return None
    finally:
        # 清理本次临时生成的 HTML 源
        if html_path is None and html is not None:
            try:
                html.unlink(missing_ok=True)
            except OSError:
                pass


# 与 markmap-cli 锁定同一小版本，保证 notes / meeting 导图观感一致
_MARKMAP_LIB_CDN = (
    f"https://cdn.jsdelivr.net/npm/markmap-lib@{_MARKMAP_CLI_VERSION}/dist/browser/index.js"
)
_MARKMAP_VIEW_CDN = (
    f"https://cdn.jsdelivr.net/npm/markmap-view@{_MARKMAP_CLI_VERSION}/dist/browser/index.js"
)
_MARKMAP_TOOLBAR_CDN = (
    f"https://cdn.jsdelivr.net/npm/markmap-toolbar@{_MARKMAP_CLI_VERSION}/dist/index.js"
)
_D3_CDN = "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"




def outline_to_markmap_data(outline: str) -> dict:
    """把 #/##/###/- 大纲转成 markmap-view 的 {content, children} 树。"""
    cleaned = sanitize_mindmap_outline(outline or "") or "# 思维导图"
    root: dict = {"content": "思维导图", "children": []}
    stack: list[tuple[int, dict]] = [(0, root)]
    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if not m:
                continue
            level = min(len(m.group(1)), 4)
            node = {"content": m.group(2).strip() or "未命名", "children": []}
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack[-1][1].setdefault("children", []).append(node)
            stack.append((level, node))
            continue
        if line.startswith(("- ", "* ", "+ ")):
            body = line[2:].strip()
            if not body:
                continue
            stack[-1][1].setdefault("children", []).append(
                {"content": body, "children": []}
            )
    if len(root.get("children") or []) == 1 and not (root["children"][0].get("children") is None):
        return root["children"][0]
    return root


def build_editable_mindmap_embed(
    outline: str,
    title: str = "思维导图",
) -> str:
    """可编辑思维导图：只依赖 d3 + markmap-view，不依赖会 404 的 markmap-lib。"""
    from html import escape
    from json import dumps

    cleaned = sanitize_mindmap_outline(outline or "") or "# 思维导图"
    heading = (title or "").strip() or "思维导图"
    tree = outline_to_markmap_data(cleaned)
    payload = dumps({"outline": cleaned, "tree": tree}, ensure_ascii=False)
    page_title = dumps(heading, ensure_ascii=False)
    return f"""<div class="lc-mm">
  <div class="lc-mm-bar">
    <strong>{escape(heading)}</strong>
    <span class="lc-mm-hint">滚轮缩放 · 点圆点展开/折叠 · 可编辑大纲后保存本页</span>
    <button type="button" id="lc-mm-toggle">编辑大纲</button>
    <button type="button" id="lc-mm-apply">应用</button>
    <button type="button" class="lc-mm-save" id="lc-mm-save">保存本页</button>
  </div>
  <div class="lc-mm-body" id="lc-mm-body">
    <textarea id="lc-mm-editor" spellcheck="false"></textarea>
    <div class="lc-mm-canvas">
      <svg id="lc-mindmap"></svg>
      <div id="lc-mm-fallback" class="lc-mm-fallback" hidden></div>
    </div>
  </div>
</div>
<script type="application/json" id="lc-mm-data">{payload}</script>
<script>
(function () {{
  const PAGE_TITLE = {page_title};
  const dataEl = document.getElementById('lc-mm-data');
  const editor = document.getElementById('lc-mm-editor');
  const body = document.getElementById('lc-mm-body');
  const hint = document.querySelector('.lc-mm-hint');
  const svg = document.getElementById('lc-mindmap');
  const fallback = document.getElementById('lc-mm-fallback');
  if (!dataEl || !editor || !body || !svg) return;
  const pack = JSON.parse(dataEl.textContent || '{{}}');
  editor.value = pack.outline || '';

  const parseOutline = (md) => {{
    const root = {{ content: '思维导图', children: [] }};
    const stack = [{{ level: 0, node: root }}];
    String(md || '').split(/\\r?\\n/).forEach((raw) => {{
      const line = raw.trim();
      if (!line) return;
      const hm = line.match(/^(#{{1,6}})\\s+(.*)$/);
      if (hm) {{
        const level = Math.min(hm[1].length, 4);
        const node = {{ content: hm[2].trim() || '未命名', children: [] }};
        while (stack.length && stack[stack.length - 1].level >= level) stack.pop();
        stack[stack.length - 1].node.children.push(node);
        stack.push({{ level, node }});
        return;
      }}
      if (/^[-*+]\\s+/.test(line)) {{
        const text = line.replace(/^[-*+]\\s+/, '').trim();
        if (text) stack[stack.length - 1].node.children.push({{ content: text, children: [] }});
      }}
    }});
    if (root.children.length === 1) return root.children[0];
    return root;
  }};

  const renderFallback = (tree) => {{
    const walk = (node) => {{
      const kids = node.children || [];
      const inner = kids.map(walk).join('');
      return '<li><span>' + String(node.content || '').replace(/[&<>]/g, (ch) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;'
      }})[ch]) + '</span>' + (inner ? '<ul>' + inner + '</ul>' : '') + '</li>';
    }};
    fallback.innerHTML = '<ul class="lc-mm-tree">' + walk(tree) + '</ul>';
    fallback.hidden = false;
    svg.style.display = 'none';
  }};

  const render = async (md) => {{
    const tree = parseOutline(md);
    const Markmap = window.markmap && window.markmap.Markmap;
    if (!Markmap || typeof window.d3 === 'undefined') {{
      if (hint) hint.textContent = '图谱脚本未加载，已改用列表显示。可编辑大纲后保存。';
      renderFallback(tree);
      return;
    }}
    fallback.hidden = true;
    svg.style.display = 'block';
    if (!window.__lcMarkmap) {{
      window.__lcMarkmap = Markmap.create(svg, {{ autoFit: true, duration: 0 }});
    }}
    await window.__lcMarkmap.setData(tree);
    await window.__lcMarkmap.fit();
  }};

  render(editor.value).catch((err) => {{
    console.error(err);
    renderFallback(parseOutline(editor.value));
  }});
  document.getElementById('lc-mm-toggle').onclick = () => {{
    body.classList.toggle('editing');
    document.getElementById('lc-mm-toggle').textContent =
      body.classList.contains('editing') ? '收起大纲' : '编辑大纲';
    setTimeout(() => {{ if (window.__lcMarkmap) window.__lcMarkmap.fit(); }}, 60);
  }};
  document.getElementById('lc-mm-apply').onclick = () => render(editor.value);
  editor.addEventListener('keydown', (ev) => {{
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {{
      ev.preventDefault();
      render(editor.value);
    }}
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {{
      ev.preventDefault();
      document.getElementById('lc-mm-save').click();
    }}
  }});
  document.getElementById('lc-mm-save').onclick = () => {{
    const next = editor.value;
    dataEl.textContent = JSON.stringify({{ outline: next, tree: parseOutline(next) }});
    const blob = new Blob(
      ['<!doctype html>\\n', document.documentElement.outerHTML],
      {{ type: 'text/html;charset=utf-8' }}
    );
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (document.title || PAGE_TITLE || '思维导图') + '.html';
    a.click();
    URL.revokeObjectURL(a.href);
  }};
}})();
</script>"""


__all__ = [
    "build_editable_mindmap_embed",
    "markmap_available",
    "mindmap_png_available",
    "outline_to_markmap_data",
    "sanitize_mindmap_outline",
    "factor_common_prefixes",
    "render_mindmap_html",
    "render_mindmap_png",
]

