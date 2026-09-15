"""定位页眉：对指定图片跑真实 OCR，打印每行文本 + 页面相对位置 + 引擎 chrome 判据结果。

用法：python tools/scripts/check_header.py [图片名 ...]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import load_env  # noqa: E402

load_env()

from tools.ocr.paddle_ocr import _HEADER_RE, _is_paddle_chrome  # noqa: E402
from tools.ocr.layout import ocr_image_lines  # noqa: E402

DOCS = ROOT / "data" / "1" / "docs"
NAMES = sys.argv[1:] or ["U202314751_1.jpg"]


def rect(bbox):
    if not bbox:
        return None
    xs = [float(p[0]) for p in bbox]
    ys = [float(p[1]) for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)


for name in NAMES:
    path = DOCS / name
    lines = ocr_image_lines(str(path))
    rects = [rect(l.get("bbox")) for l in lines]
    tops = [r[1] for r in rects if r]
    bottoms = [r[3] for r in rects if r]
    span_top, span_bottom = (min(tops), max(bottoms)) if tops else (0, 1)
    span = max(1.0, span_bottom - span_top)
    print(f"\n{'=' * 78}\n### {name}（{len(lines)} 行，检测行范围 {span_top:.0f}~{span_bottom:.0f}）\n{'=' * 78}")
    for idx, (line, r) in enumerate(zip(lines, rects)):
        text = str(line.get("text") or "")
        y0 = (r[1] - span_top) / span if r else -1
        y1 = (r[3] - span_top) / span if r else -1
        # 命中引擎 chrome 判据吗（判据内部用图片尺寸算，这里只标相对位置）
        t = "".join(text.split())
        hit = bool(_HEADER_RE.search(t)) if t else False
        mark = ""
        if y0 <= 0.15 or y1 >= 0.85:
            mark = "  ← 边缘带"
        if hit:
            mark += "  ★命中机构/联系式正则"
        print(f"  [{idx:2d}] y={y0:5.2f}~{y1:5.2f} {text[:46]!r}{mark}")
