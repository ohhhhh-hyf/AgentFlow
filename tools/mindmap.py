"""mindmap.py —— 思维导图 HTML 生成（markmap-cli 封装，无痛降级）。

把 Markdown 大纲（mindmap 任务线的 outline 字段）渲染为交互式
HTML 思维导图（markmap）：

- 依赖：Node + npx（``npx --yes markmap-cli`` 首次自动下载，无需全局安装）
- 产物：``--offline`` 单文件 HTML，所有 JS/CSS 内联，可离线打开/分享
- 设计约束（沿用 tools/template_router.py 的无痛惯例）：
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
    outline = (outline or "").strip()
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


def _png_color_count(path: Path, sample_every: int = 4) -> int:
    """兼容旧调用：仅返回采样颜色数。"""
    return _png_pixel_stats(path, sample_every=sample_every)[0]


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
    outline = (outline or "").strip()
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


__all__ = [
    "markmap_available",
    "mindmap_png_available",
    "render_mindmap_html",
    "render_mindmap_png",
]

