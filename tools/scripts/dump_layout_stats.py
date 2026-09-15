"""打印若干图片的版面统计：每行的 y、行高、置信度，用于设计"每图自适应"的页眉判据。"""
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.config import load_env  # noqa: E402

load_env()
from tools.ocr.layout import ocr_image_lines  # noqa: E402

DOCS = ROOT / "data" / "1" / "docs"
NAMES = [f"U202314751_{i}.jpg" for i in (15, 16)]
HEADER_HINT = ("科技", "UNIVERSITY", "Wuhan", "印刷厂", "華中", "华中")


def rect(bbox):
    if not bbox:
        return None
    xs = [float(p[0]) for p in bbox]
    ys = [float(p[1]) for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)


for name in NAMES:
    lines = ocr_image_lines(str(DOCS / name))
    rects = [rect(l.get("bbox")) for l in lines]
    ok = [(l, r) for l, r in zip(lines, rects) if r]
    heights = [r[3] - r[1] for _l, r in ok]
    h_med = statistics.median(heights) if heights else 1.0
    confs = [float(l.get("conf") or 0) for l, _r in ok]
    c_med = statistics.median(confs) if confs else 0.0
    span_top = min(r[1] for _l, r in ok) if ok else 0.0
    span_bottom = max(r[3] for _l, r in ok) if ok else 1.0
    span = max(1.0, span_bottom - span_top)
    print(f"\n{'=' * 82}")
    print(f"### {name}  行数={len(ok)}  行高中位={h_med:.0f}px  置信中位={c_med:.2f}  检测范围={span_top:.0f}~{span_bottom:.0f}")
    print(f"{'=' * 82}")
    for idx, (line, r) in enumerate(zip(lines, rects)):
        text = str(line.get("text") or "")
        h = (r[3] - r[1]) if r else 0
        y0 = ((r[1] - span_top) / span) if r else -1
        conf = float(line.get("conf") or 0)
        hint = "★页眉/页脚" if any(k in text for k in HEADER_HINT) else ""
        flag = f"h={h:4.0f}({h / h_med:4.2f}x) conf={conf:.2f}" if r else "no-bbox"
        print(f"  [{idx:2d}] y={y0:5.2f} {flag} {text[:40]!r} {hint}")
