"""文档解析与分块 —— 支持 txt/md/pdf/docx/pptx/xlsx(可选 doc/ppt 转换)。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".docx", ".pptx", ".xlsx"}

# Excel 分块参数
EXCEL_ROWS_PER_CHUNK = 30
EXCEL_HEADER_DETECT_MAX_ROWS = 5
EXCEL_DATA_ROW_MIN_NUMERIC = 2
EXCEL_DATA_ROW_NUMERIC_RATIO = 0.5


@dataclass
class TextChunk:
    """单个文本块"""
    text: str
    metadata: dict = field(default_factory=dict)


# ============================================================
# 文本清洗(减少 embedding NaN / 噪声)
# ============================================================
def sanitize_text(text: str) -> str:
    """NFKC 归一化 + 剔除控制字符 + 压缩空白"""
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ============================================================
# 各格式提取
# ============================================================
def _extract_txt(path: str) -> List[TextChunk]:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        raw = Path(path).read_text(errors="ignore")
    return [TextChunk(sanitize_text(raw), {"source": Path(path).name})]


def _extract_pdf(path: str) -> List[TextChunk]:
    import pdfplumber
    chunks = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(TextChunk(
                    sanitize_text(text),
                    {"source": Path(path).name, "page": i + 1}))
    return chunks


def _extract_docx(path: str) -> List[TextChunk]:
    import docx
    doc = docx.Document(path)
    text = "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
    return [TextChunk(sanitize_text(text), {"source": Path(path).name})]


def _extract_pptx(path: str) -> List[TextChunk]:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    chunks = []
    prs = Presentation(path)
    for i, slide in enumerate(prs.slides):
        parts = []
        for shape in _iter_shapes(slide.shapes):
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                # 图片内容暂不解析，直接跳过
                continue
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = " | ".join(c.text.strip() for c in row.cells)
                    if cells.strip():
                        parts.append(cells)
        if parts:
            chunks.append(TextChunk(
                sanitize_text("\n".join(parts)),
                {"source": Path(path).name, "page": i + 1}))
    return chunks


def _iter_shapes(shapes):
    """递归遍历形状(含组合形状 group)"""
    for shape in shapes:
        yield shape
        try:
            from pptx.enum.shapes import MSO_SHAPE_TYPE
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from _iter_shapes(shape.shapes)
        except Exception:
            pass


# ============================================================
# Excel: 表头识别 + 统计摘要
# ============================================================
def _is_numeric_cell(val) -> bool:
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, str):
        s = val.strip()
        if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s):
            return True
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False


def _detect_header_rows(rows_raw) -> int:
    """启发式识别表头行数: 找到第一个「像数据行」的行号(至少 1, 最多 5)"""
    for idx, row in enumerate(rows_raw[:EXCEL_HEADER_DETECT_MAX_ROWS]):
        cells = [str(c).strip() for c in row if c is not None]
        if not cells:
            continue
        numeric = sum(1 for c in cells if _is_numeric_cell(c))
        if numeric >= EXCEL_DATA_ROW_MIN_NUMERIC and \
           numeric / len(cells) >= EXCEL_DATA_ROW_NUMERIC_RATIO:
            return max(idx, 1)
    return 1


def _excel_summary(base, sheet, sheet_idx, rows_raw, header_rows) -> TextChunk:
    """统计摘要块: 总行数/列名/每列统计/数值列 合计平均最大最小"""
    lines = [f"【统计摘要】文件: {base}，工作表: {sheet}",
             f"总数据行数: {max(len(rows_raw) - header_rows, 0)} 行（不含表头）"]
    data_rows = rows_raw[header_rows:]
    if rows_raw:
        ncol = max((len(r) for r in rows_raw), default=0)
        lines.append(f"列数: {ncol}")
        header = [str(c).strip() for c in rows_raw[0][:ncol] if c is not None]
        if header:
            lines.append("表头列名: " + ", ".join(header))
        for col in range(ncol):
            vals = [r[col] for r in data_rows if col < len(r)]
            non_empty = [v for v in vals if v is not None and str(v).strip() != ""]
            lines.append(f"列{col+1}: {len(non_empty)}个非空值, "
                         f"{len(set(str(v) for v in non_empty))}个不同值, "
                         f"{len(vals) - len(non_empty)}个空值")
            if non_empty and all(_is_numeric_cell(v) for v in non_empty):
                nums = [float(v) for v in non_empty]
                lines.append(f"    合计={sum(nums):.2f}, 平均={sum(nums)/len(nums):.2f}, "
                             f"最小={min(nums):.2f}, 最大={max(nums):.2f}")
    return TextChunk("\n".join(lines),
                     {"source": base, "sheet": sheet, "sheet_idx": sheet_idx,
                      "type": "summary"})


def _extract_xlsx(path: str) -> List[TextChunk]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    chunks = []
    for si, ws in enumerate(wb.worksheets):
        rows_raw = [[c.value for c in row] for row in ws.iter_rows()]
        rows_raw = [r for r in rows_raw if any(c is not None for c in r)]
        if not rows_raw:
            continue
        header_rows = _detect_header_rows(rows_raw)
        # 表头 + 每 N 行一块
        header = " | ".join(str(c).strip() if c is not None else "" for c in rows_raw[0])
        chunks.append(TextChunk(header, {"source": Path(path).name,
                                         "sheet": ws.title, "header": True}))
        for i in range(header_rows, len(rows_raw), EXCEL_ROWS_PER_CHUNK):
            block_rows = rows_raw[i:i + EXCEL_ROWS_PER_CHUNK]
            block = "\n".join(
                " | ".join(str(c).strip() if c is not None else "" for c in r)
                for r in block_rows)
            if block.strip():
                chunks.append(TextChunk(sanitize_text(block),
                                        {"source": Path(path).name,
                                         "sheet": ws.title,
                                         "rows": f"{i-header_rows+1}-{i+len(block_rows)-header_rows}"}))
        chunks.append(_excel_summary(Path(path).name, ws.title, si, rows_raw, header_rows))
    return chunks


# ============================================================
# 分块
# ============================================================
def split_text(chunks: List[TextChunk], chunk_size: int, chunk_overlap: int) -> List[TextChunk]:
    """把超大块按分隔符递归切分; 保留元数据, 追加 chunk_index, 过滤过短块"""
    result: List[TextChunk] = []
    for ci, chunk in enumerate(chunks):
        if len(chunk.text) <= chunk_size:
            result.append(chunk)
            continue
        pieces = _recursive_split(chunk.text, ["\n\n", "\n", "。", "；", "，", " "],
                                  chunk_size, chunk_overlap)
        for pi, piece in enumerate(pieces):
            piece = sanitize_text(piece)
            if len(piece) < 30:
                continue
            meta = dict(chunk.metadata)
            meta["chunk_index"] = f"{ci}-{pi}"
            result.append(TextChunk(piece, meta))
    return result


def _recursive_split(text: str, separators: List[str], chunk_size: int, overlap: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    sep = next((s for s in separators if s in text), None)
    if sep is None:
        step = max(chunk_size - overlap, 1)
        return [text[i:i + chunk_size] for i in range(0, len(text), step)]
    parts = text.split(sep)
    merged, buf = [], ""
    for p in parts:
        if not buf or len(buf) + len(p) + len(sep) <= chunk_size:
            buf = (buf + sep + p) if buf else p
        else:
            merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    out: List[str] = []
    for m in merged:
        out.extend(_recursive_split(m, separators[1:], chunk_size, overlap))
    return out


# ============================================================
# 总入口
# ============================================================
def process_file(file_path: str, chunk_size: int = 500,
                 chunk_overlap: int = 100) -> List[TextChunk]:
    """解析单个文件并分块。Excel 已按行组织, 不再二次切分。"""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(
            f"不支持的文件格式 '{ext}'，支持: {', '.join(sorted(SUPPORTED_EXTS))}")

    handlers = {
        ".txt": _extract_txt,
        ".md": _extract_txt,
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".pptx": _extract_pptx,
        ".xlsx": _extract_xlsx,
    }
    chunks = handlers[ext](str(path))
    if ext in (".xlsx",):
        return chunks                       # Excel 不再 split_text
    return split_text(chunks, chunk_size, chunk_overlap)
