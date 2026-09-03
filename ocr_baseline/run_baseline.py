# -*- coding: utf-8 -*-
"""OCR 入库基线记录脚本（服务器上用 paddleocr / serverocr 各跑一次）。

跑真实生产同一条流水线（tools/ocr/levels/light.iter_logged_ocr_pipeline），
把 data/1/docs 的图片按批 OCR → LLM 整理(ocr/reconstruct) → LLM 审校(ocr/review)，
然后记录：

- 墙钟时间 / OCR 阶段 / 整理审校阶段（按批与总计）
- 两轮 LLM（按 label 分账）调用次数、耗时、token（共享 LLMClient + usage_by_label）
- 输出 md 相对 OCR 原文的保真率（正文/公式分开：字符比、kept80、整行连续、6gram recall）
- 公式定界错误（残余游离 $、$$$、\\left/\\right 不成对）
- 入库增量单元数（isolated fake KnowledgeTool + 生产 ingest_library 同款计数）

用法（在服务器仓库根目录执行；.env 配好对应 OCR 引擎与 LLM key）：
    python ocr_baseline/run_baseline.py --engine paddleocr
    python ocr_baseline/run_baseline.py --engine serverocr
    python ocr_baseline/run_baseline.py --engine paddleocr --batch-size 8 --kb-mode real

产物：ocr_baseline/records/<时间戳>_<引擎>_b<批大小>/run.json（规范数据，用于分析）
与同目录 summary.md（人读摘要）、batch_*.md/_raw.txt、merged 稿件、raw 合并稿等。

说明：不改动任何生产代码，仅以脚本复用生产模块；KB 计数默认 fake 离线伪向量
（与真实 embedding 的增量计数在空库上结果一致，且可复现、无网络依赖）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_IMAGES_DIR = ROOT / "data" / "1" / "docs"
OUTPUT_ROOT = Path(__file__).resolve().parent / "records"

_NUM_TAIL_RE = re.compile(r"(\d+)\s*$")


# ════════════════════════ 文本 / 保真度指标（纯本地，零 LLM 调用） ════════════════════════

# md 侧清除的排版字符。$ 也清除：行内/展示公式的包裹符会把参考文本切碎
# （如"当 $x$ 趋近于 $a$ 时"），它属排版而非内容，正文 recall 度量时去掉。
# LaTeX 命令与 \\ 保留（公式行单独统计，正文行不含 LaTeX）。
_MD_MARKUP_CHARS = set("#*`|>~_$")
_MATH_HINT_RE = re.compile(
    r"[=＋×÷−√∫∑∏≥≤≠≈∞πθαβλΣφΦ→←]"
    r"|\\frac|\\sum|\\int|\\lim|\\sqrt|\\left|\\right"
    r"|(?<![A-Za-z])(?:lim|sin|cos|tan|log|ln)(?![A-Za-z])"
    r"|[\^_]\s*\{?"
)
_LR_LEFT_RE = re.compile(r"\\left(?![a-zA-Z])")
_LR_RIGHT_RE = re.compile(r"\\right(?![a-zA-Z])")
_TRIPLE_DOLLAR_RE = re.compile(r"\${3,}")


def natural_key(name: str):
    m = _NUM_TAIL_RE.search(name)
    return (int(m.group(1)), name) if m else (10 ** 9, name)


def compact(text: str, strip_md: bool = False) -> str:
    """去全部空白；strip_md 时再移除 md 排版字符（用于 md 一侧）。"""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = "".join(t.split())
    if strip_md:
        t = "".join(ch for ch in t if ch not in _MD_MARKUP_CHARS)
    return t


def _ngrams(blob: str, n: int = 6) -> Counter:
    if len(blob) < n:
        return Counter()
    return Counter(blob[i : i + n] for i in range(len(blob) - n + 1))


def multiset_recall(ref_blob: str, out_blob: str, n: int = 6):
    c1 = _ngrams(compact(ref_blob), n)
    if not c1:
        return None
    c2 = _ngrams(compact(out_blob, strip_md=True), n)
    total = sum(c1.values())
    hit = sum(min(c1[g], c2[g]) for g in c1)
    return hit / total


def is_formula_row(row: dict) -> bool:
    if str(row.get("formula") or "").strip():
        return True
    if str(row.get("role_hint") or "") == "formula":
        return True
    return bool(_MATH_HINT_RE.search(str(row.get("text") or "")))


def line_fidelity(row: dict, md_blob: str) -> dict:
    """单条 OCR 行相对整稿 md 的保留程度（宽松口径，容忍换行合并与 md 排版）。"""
    line = compact(str(row.get("formula") or row.get("text") or ""))
    out = compact(md_blob, strip_md=True)
    if not line:
        return {"row_len": 0}
    if not out:
        return {"row_len": len(line), "avg_char_ratio": 0.0, "kept80": False, "contiguous": False}
    counts = Counter(out)
    total = 0
    hit = 0
    for ch in line:
        total += 1
        if counts.get(ch, 0) > 0:
            hit += 1
            counts[ch] -= 1
    ratio = hit / total if total else 0.0
    return {
        "row_len": len(line),
        "avg_char_ratio": ratio,
        "kept80": ratio >= 0.8,
        "contiguous": line in out,
    }


def aggregate_fidelity(rows: list[dict], md_blob: str) -> dict:
    """rows=整理输入的 OCR 行（已剔除页眉页脚），md=该批整理稿/全稿。"""
    text_rows: list[dict] = []
    formula_rows: list[dict] = []
    for row in rows:
        if not compact(str(row.get("formula") or row.get("text") or "")):
            continue
        (formula_rows if is_formula_row(row) else text_rows).append(row)

    def _sum(part: list[dict]) -> dict:
        if not part:
            return {"rows": 0}
        stats = [line_fidelity(r, md_blob) for r in part]
        stats = [s for s in stats if s.get("row_len", 0) >= 3]
        if not stats:
            return {"rows": 0}
        return {
            "rows": len(stats),
            "avg_char_ratio": round(
                sum(s["avg_char_ratio"] for s in stats) / len(stats), 4
            ),
            "kept80_ratio": round(sum(1 for s in stats if s["kept80"]) / len(stats), 4),
            "contiguous_ratio": round(
                sum(1 for s in stats if s["contiguous"]) / len(stats), 4
            ),
        }

    ref_text = "\n".join(str(r.get("formula") or r.get("text") or "") for r in text_rows)
    ref_all = "\n".join(
        str(r.get("formula") or r.get("text") or "") for r in (text_rows + formula_rows)
    )
    return {
        "text": _sum(text_rows),
        "formula": _sum(formula_rows),
        "recall6_text": multiset_recall(ref_text, md_blob),
        "recall6_all": multiset_recall(ref_all, md_blob),
    }


def scan_formula_delimiters(md: str) -> dict:
    """统计 md 公式定界：块数量与残余错误（口径与 tools/ocr/mathmd 归一化一致）。"""
    out = {
        "inline_blocks": 0,
        "display_blocks": 0,
        "stray_dollar": 0,
        "triple_dollar_spots": 0,
        "lr_mismatch_bodies": 0,
        "lr_mismatch_ops": 0,
    }
    text = md or ""
    out["triple_dollar_spots"] = len(_TRIPLE_DOLLAR_RE.findall(text))
    i = 0
    n = len(text)
    bodies: list[str] = []
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "`":
            # 代码围栏/行内码内的 $ 不算公式
            if text.startswith("```", i):
                end = text.find("```", i + 3)
                i = n if end < 0 else end + 3
                continue
            end = text.find("`", i + 1)
            i = n if end < 0 else end + 1
            continue
        if text.startswith("$$", i):
            closer = _find_closer(text, i + 2, display=True)
            if closer is None:
                out["stray_dollar"] += 2
                i += 2
                continue
            body, end = closer
            out["display_blocks"] += 1
            bodies.append(body)
            i = end
            continue
        if ch == "$":
            closer = _find_closer(text, i + 1, display=False)
            if closer is None:
                out["stray_dollar"] += 1
                i += 1
                continue
            body, end = closer
            out["inline_blocks"] += 1
            bodies.append(body)
            i = end
            continue
        i += 1
    for body in bodies:
        lefts = len(_LR_LEFT_RE.findall(body))
        rights = len(_LR_RIGHT_RE.findall(body))
        if lefts != rights:
            out["lr_mismatch_bodies"] += 1
            out["lr_mismatch_ops"] += abs(lefts - rights)
    return out


def _find_closer(text: str, start: int, *, display: bool):
    """与 tools/ocr/mathmd 一致：display 允许单 $ 收尾；inline 遇空行视为未闭合。"""
    j = start
    while j < len(text):
        if text[j] == "\\":
            j += 2
            continue
        if not display and text.startswith("\n\n", j):
            return None
        if display and text.startswith("$$", j):
            return text[start:j], j + 2
        if display and text[j] == "$":
            return text[start:j], j + 1
        if not display and text.startswith("$$", j):
            return text[start:j], j + 2
        if not display and text[j] == "$":
            return text[start:j], j + 1
        j += 1
    return None


def md_structure_counts(md: str) -> dict:
    headings = Counter()
    table_rows = 0
    for line in (md or "").splitlines():
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            headings[len(m.group(1))] += 1
        if "|" in line and line.strip().startswith("|"):
            table_rows += 1
    return {
        "headings_by_level": {str(k): headings[k] for k in sorted(headings)},
        "heading_total": sum(headings.values()),
        "table_rows": table_rows,
        "bold_ops": (md or "").count("**") // 2,
        "lines": len((md or "").splitlines()),
        "chars": len(md or ""),
    }


# ═══════════════════════════ LLM 调用记录（共享 client + label） ═══════════════════════════

class _RecordingLLM:
    """代理共享 LLMClient：逐调用记录 label / 耗时，并归因到批号。

    client.text 是 async 方法，代理必须也是 async 并 await 真实调用，
    否则计时会在协程真正执行前完成（asyncio.run 包装的是返回值协程）。
    注意：页级整理并发时，逐调用 usage 差分会因窗口交叠而失真，
    所以本代理**不做逐调用 token 差分**——token 一律以客户端快照
    （usage_by_label，锁内累计）为准，见 main() 的 _llm_label_stats 合并。"""

    def __init__(self, real) -> None:
        self.real = real
        self.calls: list[dict] = []
        self.active_batch = None
        self.failures_by_label: Counter = Counter()

    def __getattr__(self, name):
        return getattr(self.real, name)

    async def text(self, system_prompt, user_prompt, **kwargs):
        label = str(kwargs.get("label") or "text")
        batch = self.active_batch
        t0 = time.monotonic()
        try:
            result = await self.real.text(system_prompt, user_prompt, **kwargs)
        except BaseException as exc:  # noqa: BLE001 生产内部有重试与降级，这里只记录
            self.failures_by_label[label] += 1
            self.calls.append(
                {
                    "batch": batch,
                    "label": label,
                    "ok": False,
                    "seconds": round(time.monotonic() - t0, 3),
                    "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                }
            )
            raise
        self.calls.append(
            {
                "batch": batch,
                "label": label,
                "ok": True,
                "seconds": round(time.monotonic() - t0, 3),
            }
        )
        return result

    def structured(self, *args, **kwargs):
        return self.real.structured(*args, **kwargs)


def _patch_shared_llm():
    """让 OCR 整理/审校内部的 get_llm_client() 都命中同一个带记录的共享 client。

    生产代码每次调用都新建 LLMClient（label 统计随实例丢失）；
    基线仅在本进程内改为共享实例，不改生产文件。"""
    import tools.ocr.engines as engines_mod

    original = engines_mod.get_llm_client
    holder: dict = {"shared": None}

    def shared_factory():
        if holder["shared"] is None:
            real = original()
            if real is None:
                return None
            holder["shared"] = _RecordingLLM(real)
        return holder["shared"]

    engines_mod.get_llm_client = shared_factory
    return holder


# ═══════════════════════════════════════ 主流程 ═══════════════════════════════════════

def _resolve_images(args) -> list[Path]:
    if args.images:
        found = [Path(p) for p in args.images]
        missing = [p for p in found if not p.exists()]
        if missing:
            raise SystemExit(f"图片不存在：{missing[0]}")
        return found
    folder = Path(args.image_dir) if args.image_dir else DEFAULT_IMAGES_DIR
    files = sorted(
        [p for p in folder.glob("*.jpg")]
        + [p for p in folder.glob("*.jpeg")]
        + [p for p in folder.glob("*.png")],
        key=lambda p: natural_key(p.name),
    )
    if not files:
        raise SystemExit(f"目录里没有图片：{folder}")
    return files


def _configure_engine(args) -> dict:
    from client.config import load_env

    load_env(ROOT / ".env")
    from tools.ocr import engines

    engine_before = engines.ocr_engine_label()
    if args.engine:
        alias = str(args.engine).strip().lower()
        if alias not in engines._ENGINE_ALIASES:
            raise SystemExit(f"未知 OCR 引擎 {alias!r}（可选：paddleocr / serverocr / rapidocr）")
        os.environ["OCR_ENGINE"] = alias
    label = engines.ocr_engine_label()
    if args.workers:
        if label == "paddleocr":
            os.environ["PADDLE_OCR_POOL_SIZE"] = str(args.workers)
        else:
            os.environ["OCR_PARALLEL"] = str(args.workers)
    concurrency = engines.ocr_concurrency()
    return {
        "engine_before": engine_before,
        "engine": label,
        "ocr_concurrency": concurrency,
    }


def _paddle_warmup(label: str, concurrency: int) -> None:
    if label != "paddleocr" or concurrency < 1:
        return
    from tools.ocr.paddle_ocr import warmup_engines

    try:
        warmup_engines()
    except Exception as exc:  # noqa: BLE001
        print(f"[baseline] paddle 预热失败（不阻断）：{exc}", flush=True)


def run_pipeline(images, *, batch_size: int, item_timeout, holder, out_dir):
    """跑生产流水线；返回 {阶段统计, 批记录, 每图记录, 参考行池, 文本产物}。"""
    from tools.ocr.levels import light

    def current_recorder():
        # recorder 惰性创建（首次 get_llm_client 时实例化），每次取当前共享实例
        return holder.get("shared") if holder else None

    per_image: list[dict] = []
    ocr_failures: list[dict] = []
    batches: list[dict] = []
    merged_blocks: list[str] = []
    raw_blocks: list[str] = []
    ref_rows_pool: list[dict] = []          # 全稿保真参考行（跨批累计）
    stage = {"ocr_seconds": 0.0, "review_seconds": 0.0}
    ocr_batch_stage: list[dict] = []        # 每批 OCR 阶段耗时（与 batches 按序 1:1）
    events_seen: Counter = Counter()

    def measured_ocr(path: str):
        t0 = time.monotonic()
        name = Path(path).name
        try:
            raw_text, lines = light.ocr_image_to_lines(path)
            err = ""
        except BaseException as exc:  # noqa: BLE001
            raw_text, lines, err = "（OCR 未识别到文字）", [], f"{type(exc).__name__}: {str(exc)[:200]}"
        confs = [float(item["conf"]) for item in lines if item.get("conf") is not None]
        per_image.append(
            {
                "name": name,
                "ok": not err,
                "seconds": round(time.monotonic() - t0, 3),
                "error": err,
                "lines": len(lines),
                "text_chars": len(raw_text),
                "avg_conf": round(sum(confs) / len(confs), 4) if confs else None,
                "min_conf": round(min(confs), 4) if confs else None,
                "formula_lines": sum(1 for item in lines if is_formula_row(item)),
            }
        )
        return raw_text, lines

    batch_seq: dict = {"index": 0}
    opened: dict = {"lo": 0, "hi": 0}

    def batch_review(pages: list[dict]) -> str:
        """一组的整理+审校（生产函数），前后量门控/耗时/保真度。"""
        batch_seq["index"] += 1
        idx = batch_seq["index"]
        lines = light.concat_page_lines(pages)
        ref_rows = [
            item
            for item in lines
            if str(item.get("role_hint") or "") != "boilerplate"
            and str(item.get("text") or item.get("formula") or "").strip()
        ]
        t0 = time.monotonic()
        reviewed = light.reconstruct_and_review_pages(pages)
        rec = {
            "index": idx,
            "lo": opened["lo"],
            "hi": opened["hi"],
            "pages": len(pages),
            "needs_reconstruct_llm": bool(light._needs_reconstruct_llm(lines)),
            "needs_review_llm": bool(light._needs_review(lines)),
            "reconstruct_est_max_tokens": light._estimate_reconstruct_tokens(lines),
            "review_fn_seconds": round(time.monotonic() - t0, 3),
            "md_chars": len(reviewed),
            "ref_rows": len(ref_rows),
            "ref_chars": sum(len(str(r.get("formula") or r.get("text") or "")) for r in ref_rows),
            "fidelity": aggregate_fidelity(ref_rows, reviewed),
            "formulas": scan_formula_delimiters(reviewed),
            "structure": md_structure_counts(reviewed),
        }
        batches.append(rec)
        ref_rows_pool.extend(ref_rows)
        raw_block = light.combine_ocr_pages(pages, key="raw_text")
        merged_blocks.append(reviewed)
        raw_blocks.append(raw_block)
        (out_dir / f"batch_{idx:02d}_raw.txt").write_text(raw_block, encoding="utf-8")
        (out_dir / f"batch_{idx:02d}_reviewed.md").write_text(reviewed, encoding="utf-8")
        return reviewed

    def review_with_batch(pages: list[dict]) -> str:
        # LLM 记录器在调用期间绑定当前批号（调用是串行的，安全）
        rec = current_recorder()
        prev = rec.active_batch if rec is not None else None
        if rec is not None:
            rec.active_batch = batch_seq["index"] + 1
        try:
            return batch_review(pages)
        finally:
            if rec is not None:
                rec.active_batch = prev

    phase = None
    phase_t = 0.0
    batch_open: dict | None = None  # {"lo","hi","t"}

    def on_event(ev: dict) -> None:
        nonlocal phase, phase_t, batch_open
        now = time.monotonic()
        kind = ev.get("type")
        events_seen[kind] += 1
        if kind == "ocr_start":
            lo, hi = int(ev.get("lo") or 0), int(ev.get("hi") or 0)
            opened["lo"], opened["hi"] = lo, hi
            if phase == "review":
                stage["review_seconds"] += now - phase_t
            if phase == "ocr" and batch_open:
                stage["ocr_seconds"] += now - batch_open["t"]
                batch_open = None
            phase, phase_t = "ocr", now
            batch_open = {"lo": lo, "hi": hi, "t": now}
        elif kind == "review_start":
            if phase == "ocr" and batch_open:
                stage["ocr_seconds"] += now - batch_open["t"]
                ocr_batch_stage.append(
                    {"lo": batch_open["lo"], "hi": batch_open["hi"],
                     "seconds": round(now - batch_open["t"], 3)}
                )
                batch_open = None
            phase, phase_t = "review", now
        elif kind == "batch_done":
            if phase == "review":
                stage["review_seconds"] += now - phase_t
                phase = None
        elif kind == "ocr_fail":
            ocr_failures.append(
                {"name": ev.get("name"), "page": ev.get("page"), "error": ev.get("error")}
            )

    kwargs = {"batch_size": max(1, min(batch_size, len(images)))}
    if item_timeout:
        kwargs["item_timeout"] = item_timeout
    for ev in light.iter_logged_ocr_pipeline(
        [(p, p.name) for p in images], ocr_fn=measured_ocr, review_fn=review_with_batch, **kwargs
    ):
        on_event(ev)
    if phase == "ocr" and batch_open:
        stage["ocr_seconds"] += time.monotonic() - batch_open["t"]
    elif phase == "review":
        stage["review_seconds"] += time.monotonic() - phase_t

    return {
        "stage": stage,
        "ocr_batch_stage": ocr_batch_stage,
        "batches": batches,
        "per_image": sorted(per_image, key=lambda r: natural_key(r["name"])),
        "ocr_failures": ocr_failures,
        "events_seen": dict(events_seen),
        "merged_blocks": merged_blocks,
        "raw_blocks": raw_blocks,
        "ref_rows_pool": ref_rows_pool,
    }


def _kb_ingest(md_file: Path, *, engine: str, kb_mode: str, out_dir: Path) -> dict:
    """生产同款「md 文件入库 + 知识单元计数」（isolated 库，不污染真实数据）。"""
    from domain.notes.tasks.library.report import ingest_library, kb_from_env

    user_id = "ocr_baseline"
    subject = f"base_{engine}"
    result: dict = {
        "mode": "fake" if kb_mode != "real" else "real",
        "user_id": user_id,
        "subject": subject,
        "ok": False,
    }
    os.environ["KNOWLEDGE_PERSIST_DIR"] = str(out_dir / "kb_chroma")

    def _run(fake: bool) -> None:
        os.environ["KNOWLEDGE_FAKE"] = "1" if fake else "0"
        kb = kb_from_env(user_id=user_id)
        t0 = time.monotonic()
        data = ingest_library(kb, [md_file], user_id=user_id, subject=subject)
        result.update(data)
        result["ok"] = True
        result["seconds"] = round(time.monotonic() - t0, 3)

    try:
        _run(kb_mode != "real")
    except Exception as exc:  # noqa: BLE001  key 缺失/网络失败 → 自动降级 fake 并注明
        result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}（自动降级 fake 重试）"
        try:
            _run(True)
        except Exception as exc2:  # noqa: BLE001
            result["error"] += f"；fake 也失败：{type(exc2).__name__}: {str(exc2)[:200]}"
    return result


def _llm_label_stats(calls: list[dict], usage_by_label: dict | None = None) -> dict:
    """按 label 汇总。次数/耗时来自逐调用记录（并发下 seconds 是各调用耗时之和，
    可大于墙钟，墙钟以 wall.review_seconds 为准）；token 一律取自客户端快照
    usage_by_label（锁内累计，并发安全），避免逐调用差分交叠失真。"""
    usage_by_label = usage_by_label or {}
    out: dict = {}
    for call in calls:
        slot = out.setdefault(
            call["label"],
            {
                "calls": 0, "ok_calls": 0, "fail_calls": 0, "seconds": 0.0,
                "max_seconds": 0.0, "prompt_tokens": 0, "completion_tokens": 0,
                "total_tokens": 0, "cache_hit_tokens": 0,
            },
        )
        slot["calls"] += 1
        slot["ok_calls"] += 1 if call.get("ok") else 0
        slot["fail_calls"] += 0 if call.get("ok") else 1
        secs = float(call.get("seconds") or 0)
        slot["seconds"] += secs
        slot["max_seconds"] = max(slot["max_seconds"], secs)
    for label, slot in out.items():
        usage = usage_by_label.get(label) or {}
        slot["prompt_tokens"] = int(usage.get("prompt_tokens") or 0)
        slot["completion_tokens"] = int(usage.get("completion_tokens") or 0)
        slot["total_tokens"] = int(usage.get("total_tokens") or 0)
        slot["cache_hit_tokens"] = int(usage.get("cache_hit_tokens") or 0)
        slot["avg_seconds"] = round(slot["seconds"] / slot["calls"], 3) if slot["calls"] else 0.0
        slot["seconds"] = round(slot["seconds"], 3)
    return out


def _print_summary(run: dict, out_dir: Path) -> None:
    cfg, wall = run["config"], run["wall"]
    print("\n" + "=" * 72, flush=True)
    print(f"[baseline] {cfg['engine']} · {cfg['images']} 张 · 批 {cfg['batch_size']}"
          f"（{cfg['batch_count']} 批）· 并发 {cfg['ocr_concurrency']}"
          f" · LLM {cfg.get('llm_available')} · kb {run['ingest'].get('mode')}", flush=True)
    print(f"墙钟 {wall['total_seconds']:.1f}s | OCR {wall['ocr_seconds']:.1f}s | "
          f"整理+审校 {wall['review_seconds']:.1f}s | 入库 {wall['ingest_seconds']:.1f}s", flush=True)
    for label, slot in run["llm_by_label"].items():
        print(
            f"  LLM[{label}] {slot['calls']} 次 总 {slot['seconds']:.1f}s "
            f"(avg {slot['avg_seconds']:.1f}s max {slot['max_seconds']:.1f}s) "
            f"输入 {slot['prompt_tokens']} tok 输出 {slot['completion_tokens']} tok",
            flush=True,
        )
    if not run["llm_by_label"]:
        print("  LLM 无调用（全程走确定性路径或 LLM 不可用）", flush=True)
    wf, wfr = run["whole"]["fidelity"], run["whole"]["formulas"]
    print(
        f"保真: 正文 {wf['text'].get('rows', 0)} 行 avg_char {wf['text'].get('avg_char_ratio', float('nan')):.3f} "
        f"kept80 {wf['text'].get('kept80_ratio', float('nan')):.3f} "
        f"contiguous {wf['text'].get('contiguous_ratio', float('nan')):.3f} | "
        f"6gram(text) {wf.get('recall6_text')} (all) {wf.get('recall6_all')} | "
        f"公式 {wf['formula'].get('rows', 0)} 行 avg_char {wf['formula'].get('avg_char_ratio', float('nan')):.3f}",
        flush=True,
    )
    print(
        f"公式定界: display {wfr['display_blocks']} inline {wfr['inline_blocks']} | "
        f"游离$ {wfr['stray_dollar']} $$$ {wfr['triple_dollar_spots']} "
        f"left/right 失配 {wfr['lr_mismatch_bodies']} 处",
        flush=True,
    )
    files = run["ingest"].get("files") or []
    added = files[0].get("added") if files else "-"
    print(f"入库(fake/real={run['ingest'].get('mode')}): md 新增 {added} 块，"
          f"知识单元增量 {run['ingest'].get('increment', '-')}"
          f"（items {len(run['ingest'].get('items') or [])}）", flush=True)
    print(f"记录已写入：{out_dir / 'run.json'}", flush=True)
    print("=" * 72, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="OCR 入库基线：跑生产流水线并记录指标")
    ap.add_argument("--engine", default=None,
                    help="OCR 引擎：paddleocr / serverocr / rapidocr（默认 .env 的 OCR_ENGINE）")
    ap.add_argument("--images", nargs="*", default=None, help="图片路径列表")
    ap.add_argument("--image-dir", default=None, help="图片目录（与 --images 二选一，默认 data/1/docs）")
    ap.add_argument("--batch-size", type=int, default=8, help="整理批大小（生产默认 8）")
    ap.add_argument("--workers", type=int, default=None, help="OCR 并发路数（默认引擎配置）")
    ap.add_argument("--item-timeout", type=float, default=None,
                    help="单张 OCR 超时秒数（默认 OCR_ITEM_TIMEOUT=180）")
    ap.add_argument("--kb-mode", choices=["fake", "real"], default="fake",
                    help="入库计数库：fake=离线伪向量（默认，可复现）；real=真实 embedding（需硅基流动 key）")
    ap.add_argument("--label", default="", help="运行备注，追加进目录名")
    ap.add_argument("--set-env", action="append", default=[], metavar="KEY=VALUE",
                    help="运行前设置环境变量（如 OCR_PAGE_RECONSTRUCT=0），shell 无关，可重复")
    args = ap.parse_args()

    env_overrides: dict[str, str] = {}
    for item in args.set_env or []:
        if "=" not in item:
            raise SystemExit(f"--set-env 需 KEY=VALUE 形式：{item!r}")
        key, value = item.split("=", 1)
        env_overrides[key.strip()] = value.strip()
    os.environ.update(env_overrides)
    if env_overrides:
        print(f"[baseline] 环境覆盖：{env_overrides}", flush=True)

    settings = _configure_engine(args)
    images = _resolve_images(args)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.label}" if args.label else ""
    out_dir = OUTPUT_ROOT / f"{stamp}_{settings['engine']}_b{args.batch_size}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[baseline] 引擎 {settings['engine']}（env 原值 {settings['engine_before']}），"
          f"{len(images)} 张，批 {args.batch_size}，并发 {settings['ocr_concurrency']}，"
          f"LLM 按 label 记录 ocr/reconstruct / ocr/review / ocr/reconstruct/fix", flush=True)
    print(f"[baseline] 记录目录：{out_dir}", flush=True)

    _paddle_warmup(settings["engine"], settings["ocr_concurrency"])

    holder = _patch_shared_llm()
    # 主动触发一次共享 client 创建：LLM 不可用时 recorder=None（流水线自动走原文/原稿降级）
    try:
        from tools.ocr import engines as _eng_mod

        _eng_mod.get_llm_client()
    except BaseException:  # noqa: BLE001
        pass
    t_wall0 = time.monotonic()
    pipe = run_pipeline(
        images, batch_size=args.batch_size, item_timeout=args.item_timeout,
        holder=holder, out_dir=out_dir,
    )
    wall_total = time.monotonic() - t_wall0
    recorder = holder.get("shared")  # 管线运行中可能才首次创建，事后取最终实例

    merged = "\n\n".join(b for b in pipe["merged_blocks"] if b.strip())
    raw_merged = "\n\n".join(b for b in pipe["raw_blocks"] if b.strip())
    merged_name = f"ocr_{stamp}.md"
    (out_dir / merged_name).write_text(merged, encoding="utf-8")
    (out_dir / "raw_merged.txt").write_text(raw_merged, encoding="utf-8")

    # 全稿指标：参考行池 = 各批整理输入的 OCR 行，md = 最终合并稿
    # （aggregate_fidelity 的 recall6_text 已按非公式参考行计算；recall6_all 为全量含公式行）
    whole = {
        "fidelity": aggregate_fidelity(pipe["ref_rows_pool"], merged),
        "formulas": scan_formula_delimiters(merged),
        "structure": md_structure_counts(merged),
        "md_chars": len(merged),
        "raw_chars": len(raw_merged),
    }

    # OCR 批耗时回填（batches 与 ocr_batch_stage 按序 1:1）；键统一用字符串
    batch_stage = {}
    for b, s in zip(pipe["batches"], pipe["ocr_batch_stage"]):
        batch_stage[str(b["index"])] = {"ocr_seconds": s["seconds"]}
    # 批内 LLM 归因回填（只含逐调用耗时之和；并发下可大于该批墙钟，token 见快照口径）
    calls = recorder.calls if recorder is not None else []
    for b in pipe["batches"]:
        llm: dict[str, float] = {}
        for c in calls:
            if c.get("batch") == b["index"]:
                llm[c["label"]] = llm.get(c["label"], 0.0) + float(c.get("seconds") or 0)
        batch_stage[str(b["index"])]["llm_seconds"] = {
            k: round(v, 3) for k, v in llm.items()
        }

    llm_snapshot = recorder.real.monitor_snapshot() if recorder is not None else None
    llm_by_label = _llm_label_stats(
        calls, (llm_snapshot or {}).get("usage_by_label") if llm_snapshot else None
    )

    # Step1 完整性自检事件（与批次数按序 1:1 归并；观测触发率与补写开销，跨语料积累证据）
    completeness_events: list[dict] = []
    try:
        from tools.ocr.reconstruct import take_completeness_events

        completeness_events = take_completeness_events()
    except Exception:  # noqa: BLE001 旧代码无该接口时跳过
        pass
    for idx, b in enumerate(pipe["batches"]):
        if idx < len(completeness_events):
            b["completeness"] = completeness_events[idx]
    if completeness_events:
        completeness_agg = {
            "batches": len(completeness_events),
            "gate_off": sum(1 for e in completeness_events if e.get("gate") == "off"),
            "triggered": sum(
                1 for e in completeness_events
                if (e.get("fired_calls") or 0) or (e.get("fallback_rows") or 0)
            ),
            "fired_calls": sum(int(e.get("fired_calls") or 0) for e in completeness_events),
            "fallback_rows": sum(int(e.get("fallback_rows") or 0) for e in completeness_events),
            "out_gain_chars": sum(int(e.get("out_gain_chars") or 0) for e in completeness_events),
            "events": completeness_events,
        }
    else:
        completeness_agg = None

    # 审校轮留痕（与批次数按序 1:1；观测审校是否空转/是否值回 token，跨语料判定）
    review_events: list[dict] = []
    try:
        from tools.ocr.levels import light as _light_mod

        review_events = _light_mod.take_review_events()
    except Exception:  # noqa: BLE001 旧代码无该接口时跳过
        pass
    for idx, b in enumerate(pipe["batches"]):
        if idx < len(review_events):
            b["review"] = review_events[idx]
    if review_events:
        review_agg = {
            "batches": len(review_events),
            "disabled": sum(1 for e in review_events if not e.get("review_enabled", True)),
            "ran": sum(1 for e in review_events if e.get("ran")),
            "draft_changed": sum(1 for e in review_events if e.get("draft_changed")),
            "applied_patches": sum(int(e.get("applied_patches") or 0) for e in review_events),
        }
    else:
        review_agg = None

    t_ingest0 = time.monotonic()
    ingest = _kb_ingest(out_dir / merged_name, engine=settings["engine"],
                        kb_mode=args.kb_mode, out_dir=out_dir)
    ingest["seconds"] = round(time.monotonic() - t_ingest0, 3)

    run = {
        "schema": "agentflow-ocr-baseline/v1",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "engine": settings["engine"],
            "engine_env_before": settings["engine_before"],
            "images": len(images),
            "image_files": [p.name for p in images],
            "batch_size": args.batch_size,
            "batch_count": len(pipe["batches"]),
            "ocr_concurrency": settings["ocr_concurrency"],
            "env_overrides": env_overrides,
            "llm_provider": (recorder.real.provider if recorder is not None else None),
            "llm_model": (recorder.real.model if recorder is not None else None),
            "llm_available": recorder is not None,
        },
        "wall": {
            "total_seconds": round(wall_total, 3),
            "ocr_seconds": round(pipe["stage"]["ocr_seconds"], 3),
            "review_seconds": round(pipe["stage"]["review_seconds"], 3),
            "llm_call_seconds": round(sum(s["seconds"] for s in llm_by_label.values()), 3),
            "ingest_seconds": ingest["seconds"],
        },
        "events_seen": pipe["events_seen"],
        "ocr_failures": pipe["ocr_failures"],
        "per_image": pipe["per_image"],
        "batches": pipe["batches"],
        "batch_stage": batch_stage,
        "llm_by_label": llm_by_label,
        "llm_calls": calls,
        "llm_client_snapshot": llm_snapshot,
        "completeness": completeness_agg,
        "review_stats": review_agg,
        "whole": whole,
        "ingest": ingest,
        "artifacts": {
            "merged_md": merged_name,
            "raw_merged_txt": "raw_merged.txt",
            "per_batch_md_raw": True,
        },
    }
    (out_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_md(run, out_dir)
    _print_summary(run, out_dir)


def _write_summary_md(run: dict, out_dir: Path) -> None:
    cfg, wall = run["config"], run["wall"]
    lines = [
        "# OCR 入库基线记录", "",
        f"- 时间：{run['run_at']}",
        f"- 引擎：{cfg['engine']}（env 原值 {cfg['engine_env_before']}）",
        f"- 图片：{cfg['images']} 张（批 {cfg['batch_size']}，共 {cfg['batch_count']} 批，OCR 并发 {cfg['ocr_concurrency']}）",
        f"- LLM：{cfg.get('llm_provider')} / {cfg.get('llm_model')}（可用 {cfg.get('llm_available')}）",
        f"- 入库计数库：{run['ingest'].get('mode')}（user {run['ingest'].get('user_id')}，subject {run['ingest'].get('subject')}）",
        "",
        "## 墙钟", "",
        f"- 总计 {wall['total_seconds']:.1f}s；OCR 阶段 {wall['ocr_seconds']:.1f}s；"
        f"整理+审校阶段 {wall['review_seconds']:.1f}s；LLM 调用合计 {wall['llm_call_seconds']:.1f}s；"
        f"入库 {wall['ingest_seconds']:.1f}s",
        "",
        "## LLM（label 分账）", "",
        "| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, s in run["llm_by_label"].items():
        lines.append(
            f"| {label} | {s['calls']} | {s['ok_calls']} | {s['fail_calls']} | {s['seconds']:.1f} | "
            f"{s['avg_seconds']:.1f} | {s['max_seconds']:.1f} | {s['prompt_tokens']} | {s['completion_tokens']} |"
        )
    if not run["llm_by_label"]:
        lines.append("_（无 LLM 调用：全程确定性路径或 LLM 不可用）_")
    lines += ["", "## 逐批", "",
              "| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | "
              "公式行avg_char | 6gram(text) | 游离$ |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for b in run["batches"]:
        bs = (run.get("batch_stage") or {}).get(str(b["index"]), {})
        llm = bs.get("llm_seconds") or {}
        fd, fr = b["fidelity"], b["formulas"]
        txt, fmu = fd["text"], fd["formula"]
        gate = f"rec={int(b['needs_reconstruct_llm'])} rev={int(b['needs_review_llm'])}"
        r6 = fd.get("recall6_text")
        lines.append(
            f"| {b['index']} | {b['pages']} | {bs.get('ocr_seconds', 0):.1f} | "
            f"{llm.get('ocr/reconstruct', 0):.1f} | {llm.get('ocr/review', 0):.1f} | {gate} | "
            f"{txt.get('rows', 0)}条/{txt.get('avg_char_ratio', float('nan'))}/{txt.get('kept80_ratio', float('nan'))} | "
            f"{fmu.get('rows', 0)}条/{fmu.get('avg_char_ratio', float('nan'))} | "
            f"{'-' if r6 is None else round(r6, 3)} | {fr['stray_dollar']} |"
        )
    wf, wfr, ws = run["whole"]["fidelity"], run["whole"]["formulas"], run["whole"]["structure"]
    ca = run.get("completeness")
    if ca:
        lines += [
            "", "## 完整性闭环（Step1 自检事件）", "",
            f"- 批次数 {ca.get('batches')}（gate_off {ca.get('gate_off')}）；触发批 {ca.get('triggered')}；"
            f"补写调用 {ca.get('fired_calls')} 次；兜底行 {ca.get('fallback_rows')}；补回字符 {ca.get('out_gain_chars')}",
            "",
        ]
    lines += [
        "", "## 全稿保真（对最终合并稿）", "",
        f"- 正文 {wf['text'].get('rows', 0)} 行：avg_char_ratio={wf['text'].get('avg_char_ratio')}，"
        f"kept80={wf['text'].get('kept80_ratio')}，contiguous={wf['text'].get('contiguous_ratio')}",
        f"- 公式 {wf['formula'].get('rows', 0)} 行：avg_char_ratio={wf['formula'].get('avg_char_ratio')}，"
        f"kept80={wf['formula'].get('kept80_ratio')}",
        f"- 6gram recall：正文 {wf.get('recall6_text')}，全量 {wf.get('recall6_all')}",
        "",
        "## 公式定界（全稿）", "",
        f"- display 块 {wfr['display_blocks']}；inline 块 {wfr['inline_blocks']}；"
        f"游离 $ {wfr['stray_dollar']}；$$$ {wfr['triple_dollar_spots']}；"
        f"\\left/\\right 失配 {wfr['lr_mismatch_bodies']} 处",
        "",
        "## 结构（全稿）", "",
        f"- md 字符 {ws['chars']}；标题 {ws['heading_total']} 个"
        f"（分级 {json.dumps(ws['headings_by_level'], ensure_ascii=False)}）；"
        f"表格行 {ws['table_rows']}；**加粗** 处 {ws['bold_ops']}",
        "",
        "## 入库（生产同款计数）", "",
        f"- 模式：{run['ingest'].get('mode')}；ok={run['ingest'].get('ok')}"
        f"{('；error=' + run['ingest']['error']) if run['ingest'].get('error') else ''}",
        f"- doc_count={run['ingest'].get('doc_count')}；新增块={json.dumps(run['ingest'].get('files') or [], ensure_ascii=False)}；"
        f"知识单元增量={run['ingest'].get('increment')}；items 示例数={len(run['ingest'].get('items') or [])}",
        "",
        "规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。", "",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
