# -*- coding: utf-8 -*-
"""backend 执行器 —— 按 Plan 分组执行任务（复用现有 runner / tools.ocr）。

- 依赖组串行、无依赖组并行（asyncio.gather）
- 上传文件落盘 data/uploads/{task_id}/，映射进任务 params（file/input）
- 状态记录：running → done / failed，含当前任务与产物清单
"""
from __future__ import annotations

import asyncio
import io
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import UploadFile

# 图片后缀：library 入库时自动先 OCR 的输入类型
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


class RealtimeLogStream(io.TextIOBase):
    """实时将标准输出按行格式化推入 task_state['logs']，记录结构化里程碑时间日志。"""

    def __init__(self, task_state: dict[str, Any], max_logs: int = 1500) -> None:
        super().__init__()
        self.task_state = task_state
        self.max_logs = max_logs
        self._buffer = ""

    def _append_log(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        import time

        if not cleaned.startswith("["):
            ts = time.strftime("%H:%M:%S")
            line_str = f"[{ts}] {cleaned}"
        else:
            line_str = cleaned
        logs = self.task_state.setdefault("logs", [])
        logs.append(line_str)
        if len(logs) > self.max_logs:
            del logs[:-self.max_logs]

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buffer += s
        if "\n" in self._buffer or "\r" in self._buffer:
            lines = self._buffer.splitlines(keepends=True)
            for line in lines[:-1]:
                self._append_log(line)
            last = lines[-1]
            if last.endswith("\n") or last.endswith("\r"):
                self._append_log(last)
                self._buffer = ""
            else:
                self._buffer = last
        return len(s)

    def flush(self) -> None:
        if self._buffer:
            self._append_log(self._buffer)
            self._buffer = ""


class TaskRunner:
    def __init__(self, root: Path, uploads_dir: Path | None = None) -> None:
        self.root = root
        self.uploads_dir = uploads_dir or (root / "data")
        self._tasks: dict[str, dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── 状态管理 ──
    def state(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def output_path(self, task_id: str, name: str) -> Path | None:
        state = self._tasks.get(task_id)
        if not state:
            return None
        for p in state.get("outputs") or []:
            if Path(p).name == name:
                return Path(p)
        return None

    def _log(self, task_id: str, msg: str) -> None:
        import time
        ts = time.strftime("%H:%M:%S")
        state = self._tasks.get(task_id)
        if state is not None:
            state.setdefault("logs", []).append(f"[{ts}] {msg}")

    # ── 提交 ──
    def submit(self, plan: Dict[str, Any], files: List[UploadFile], user_id: Optional[str] = None) -> str:
        task_id = uuid.uuid4().hex[:10]

        # 优先提取 user_id：先有 user，再有该 user 的 upload 目录
        raw_uid = (user_id or plan.get("user_id") or "").strip()
        if not raw_uid and plan.get("plan"):
            for step in plan.get("plan"):
                u = step.get("params", {}).get("user_id")
                if u:
                    raw_uid = str(u).strip()
                    break
        if not raw_uid:
            raw_uid = "default_user"

        from tools.memory.store import safe_id
        uid_safe = safe_id(raw_uid)
        user_uploads_dir = self.root / "data" / uid_safe / "uploads"
        workdir = user_uploads_dir / task_id
        workdir.mkdir(parents=True, exist_ok=True)

        # 保存上传文件，记录 文件名 → 路径
        saved: dict[str, Path] = {}
        for f in files:
            dest = workdir / f.filename
            dest.write_bytes(f.file.read())
            saved[f.filename] = dest

        self._tasks[task_id] = {
            "status": "queued",
            "message": "",
            "current": "",
            "outputs": [],
            "task_id": task_id,
            "user_id": raw_uid,
            "uid_safe": uid_safe,
            "workdir": str(workdir),
            "plan": plan,
            "client_plan": plan.get("full_plan") if isinstance(plan.get("full_plan"), dict) else plan,
            "saved": {k: str(v) for k, v in saved.items()},
            "logs": [],
            "replan_events": [],
            "plan_updated": False,
            # 执行前的产物快照：完成后只报告本次新增的产物
            "output_snapshot": self._snapshot(),
        }
        self._start(task_id)
        return task_id

    def _snapshot(self) -> set[str]:
        """当前 output/ 下全部 result_* 产物路径集合。"""
        out_root = self.root / "output"
        if not out_root.is_dir():
            return set()
        return {
            str(p)
            for p in list(out_root.rglob("result_*.md"))
            + list(out_root.rglob("result_*.html"))
        }

    def _collect_outputs(self, state: dict[str, Any]) -> None:
        """只收集本次执行（提交后）新增的产物，避免混入历史结果。"""
        before = state.get("output_snapshot") or set()
        now = self._snapshot()
        new = sorted(str(p) for p in now - before)
        state["outputs"] = new[-12:]

    def _start(self, task_id: str) -> None:
        # 必须在运行中的事件循环里调用（FastAPI async handler 满足）
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # 无运行 loop：由调用方负责调度
        loop.create_task(self._run_plan(task_id))

    # ── 执行 ──
    async def _run_plan(self, task_id: str) -> None:
        state = self._tasks[task_id]
        plan = state["plan"]
        client_plan = state.get("client_plan") or plan
        saved = {k: Path(v) for k, v in state.get("saved", {}).items()}
        entries = plan.get("plan") or []
        raw_groups = plan.get("execution")
        if not raw_groups:
            raw_groups = [[e.get("task") if isinstance(e, dict) else str(e) for e in entries]]

        state["status"] = "running"
        by_task = {str(e.get("task")): e for e in entries}
        plan_tasks = set(by_task.keys())
        import time

        ts = time.strftime("%H:%M:%S")
        state.setdefault("logs", []).append(f"[{ts}] 任务流水线已启动，共编排 {len(raw_groups)} 个执行阶段")
        try:
            for group in raw_groups:
                async def _one(entry: dict[str, Any]) -> dict[str, Any]:
                    state["current"] = f"{entry.get('task')}"
                    try:
                        return await self._run_one(task_id, entry, saved, plan_tasks)
                    except Exception as exc:  # noqa: BLE001
                        import traceback

                        tb = traceback.format_exc()
                        return {"task": entry.get("task"), "ok": False, "error": tb[-1200:]}

                group_entries = []
                for item in group:
                    tname = item.get("task") if isinstance(item, dict) else str(item)
                    if tname in by_task:
                        group_entries.append(by_task[tname])

                if not group_entries:
                    continue
                results = await asyncio.gather(*[_one(e) for e in group_entries])
                for r in results:
                    state.setdefault("results", []).append(r)
                    if not r.get("ok"):
                        raise RuntimeError(
                            f"任务 {r.get('task')} 失败：{r.get('error')}"
                        )
                self._collect_outputs(state)
                self._observe_and_replan(task_id, state, client_plan, results)
            ts_done = time.strftime("%H:%M:%S")
            state.setdefault("logs", []).append(f"[{ts_done}] 全部阶段执行完毕，产物已成功生成 ✓")
            state["status"] = "done"
            state["message"] = "全部任务完成"
        except Exception as exc:  # noqa: BLE001
            state["status"] = "failed"
            state["message"] = str(exc)
        state["current"] = ""

    def _plan_task_names(self, plan: dict[str, Any]) -> list[str]:
        return [
            str(item.get("task") or "")
            for item in (plan.get("plan") or [])
            if isinstance(item, dict) and item.get("task")
        ]

    def _first_task_params(self, plan: dict[str, Any], names: set[str]) -> dict[str, Any]:
        for item in plan.get("plan") or []:
            if isinstance(item, dict) and item.get("task") in names:
                params = item.get("params")
                return dict(params) if isinstance(params, dict) else {}
        return {}

    def _insert_client_task_before(
        self,
        plan: dict[str, Any],
        *,
        new_task: str,
        before_tasks: set[str],
        params: dict[str, Any],
        needs: list[str],
        note: str,
    ) -> bool:
        entries = plan.setdefault("plan", [])
        if not isinstance(entries, list):
            return False
        if new_task in self._plan_task_names(plan):
            return False
        insert_at = len(entries)
        for idx, item in enumerate(entries):
            if isinstance(item, dict) and item.get("task") in before_tasks:
                insert_at = idx
                break
        entries.insert(
            insert_at,
            {
                "task": new_task,
                "domain": "notes",
                "params": params,
                "missing": [],
                "optional": ["file"],
                "needs": needs,
                "note": note,
                "dynamic": True,
                "dynamic_reason": note,
            },
        )
        for item in entries:
            if isinstance(item, dict) and item.get("task") in before_tasks:
                curr_needs = list(item.get("needs") or [])
                if new_task not in curr_needs:
                    item["needs"] = [new_task if (needs and x in needs) else x for x in curr_needs]
                    if new_task not in item["needs"]:
                        item["needs"].append(new_task)
        self._rebuild_client_execution(plan)
        return True

    def _rebuild_client_execution(self, plan: dict[str, Any]) -> None:
        """按当前 plan 重建前端可展示的轻量阶段。"""
        tasks = [item for item in plan.get("plan") or [] if isinstance(item, dict)]
        names = [str(item.get("task") or "") for item in tasks]
        done: set[str] = set()
        remaining = list(tasks)
        groups: list[list[str]] = []
        while remaining:
            stage = []
            for item in remaining:
                task = str(item.get("task") or "")
                needs = {
                    str(dep)
                    for dep in (item.get("needs") or [])
                    if str(dep) in names and str(dep) != task
                }
                if needs.issubset(done):
                    stage.append(item)
            if not stage:
                stage = [remaining[0]]
            groups.append([str(item.get("task")) for item in stage if item.get("task")])
            for item in stage:
                done.add(str(item.get("task") or ""))
                remaining.remove(item)
        plan["execution"] = groups

    def _observe_and_replan(
        self,
        task_id: str,
        state: dict[str, Any],
        client_plan: dict[str, Any],
        results: list[dict[str, Any]],
    ) -> None:
        """阶段后观察：发现后续目标缺关键前置步骤时，更新返回给前端的计划。"""
        if not isinstance(client_plan, dict):
            return
        names = self._plan_task_names(client_plan)
        name_set = set(names)
        completed = {str(item.get("task") or "") for item in results if item.get("ok")}
        if not completed:
            return

        wants_catalog_based = bool(name_set & {"checklist", "quiz", "knowledge_graph"})
        missing_catalog = "catalog" not in name_set
        has_scope = self._first_task_params(
            client_plan,
            {"library", "checklist", "quiz", "knowledge_graph"},
        )
        subject = str(has_scope.get("subject") or "").strip()
        user_id = str(has_scope.get("user_id") or state.get("user_id") or "").strip()
        params = {"user_id": user_id, "subject": subject}
        params = {k: v for k, v in params.items() if v}

        if wants_catalog_based and missing_catalog and subject and user_id:
            deps = ["library"] if "library" in name_set else []
            inserted = self._insert_client_task_before(
                client_plan,
                new_task="catalog",
                before_tasks={"checklist", "quiz", "knowledge_graph"},
                params=params,
                needs=deps,
                note="动态补充：先生成知识目录，再支撑后续复习/出题/图谱任务",
            )
            if inserted:
                event = {
                    "type": "insert_task",
                    "task": "catalog",
                    "reason": "后续任务依赖知识目录，Supervisor 已动态插入目录构建阶段",
                }
                state.setdefault("replan_events", []).append(event)
                state["plan_updated"] = True
                state["client_plan"] = client_plan
                state["plan"] = client_plan
                self._log(task_id, "[动态重规划] 已插入「核心知识目录构建」阶段，用于支撑后续任务")

        # OCR 成功但结果为空时不继续假装高质量；先给出明确观察，后续可升级为 ask_user。
        for item in results:
            if item.get("task") != "ocr" or not item.get("ok"):
                continue
            out = item.get("output")
            if out and Path(str(out)).is_file() and Path(str(out)).stat().st_size == 0:
                event = {
                    "type": "ask_user",
                    "task": "ocr",
                    "reason": "OCR 产物为空，建议重新上传更清晰图片或确认继续使用空结果",
                }
                state.setdefault("replan_events", []).append(event)
                state["plan_updated"] = True
                self._log(task_id, "[动态观察] OCR 产物为空，建议补充更清晰图片后重试")

    async def _run_one(
        self,
        task_id: str,
        entry: dict[str, Any],
        saved: dict[str, Path],
        plan_tasks: set[str] | None = None,
    ) -> dict[str, Any]:
        task = str(entry.get("task") or "")
        params = dict(entry.get("params") or {})
        # 把上传文件映射进 file/input/template 参数
        for key in ("file", "input", "template"):
            vals = params.get(key)
            if isinstance(vals, list) and vals:
                resolved = []
                for v in vals:
                    if v in saved:
                        resolved.append(str(saved[v]))
                    else:
                        resolved.append(str(v))
                params[key] = resolved

        task_titles = {
            "ocr": "OCR 图片与公式识别",
            "library": "知识资料结构化入库",
            "catalog": "核心知识目录构建",
            "checklist": "考点复习清单生成",
            "quiz": "智能自测题生成",
            "knowledge_graph": "知识图谱构建",
            "minutes_generation": "多视角会议纪要生成",
            "action_items": "行动项与待办提取",
            "risk": "潜在风险分析",
            "mindmap": "交互式思维导图生成",
            "minutes_trace": "发言溯源与事实核查",
            "multi_styles": "多风格版本纪要生成",
            "review": "笔记审校与逻辑纠错",
        }
        task_label = task_titles.get(task, task)
        import time
        ts = time.strftime("%H:%M:%S")
        state = self._tasks.get(task_id, {})
        state.setdefault("logs", []).append(f"[{ts}] 启动任务阶段: [{task_label}]...")
        state["message"] = f"正在执行: {task_label}"

        # 依赖自动流转：上游产物与混合格式文件自动分类补全
        if task == "ocr":
            if not params.get("input") and saved:
                imgs = [str(p) for p in saved.values() if str(p).lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp"))]
                if imgs:
                    params["input"] = imgs
            if not params.get("output"):
                workdir = Path(state.get("workdir") or (self.root / "data" / state.get("uid_safe", "default_user") / "uploads" / task_id))
                ocr_out = workdir / "ocr_result.md"
                params["output"] = str(ocr_out)
                saved["ocr_result.md"] = ocr_out
                saved["ocr_output"] = ocr_out
            res = await self._run_ocr(task_id, params)
            ts_done = time.strftime("%H:%M:%S")
            state.setdefault("logs", []).append(f"[{ts_done}] 任务阶段 [{task_label}] 执行完成\n")
            return res

        if task == "library":
            doc_files = []
            if params.get("file"):
                raw_files = params["file"] if isinstance(params["file"], list) else [params["file"]]
                doc_files.extend(raw_files)
            elif saved:
                doc_files.extend([str(p) for p in saved.values() if not str(p).lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp"))])
            if "ocr_result.md" in saved:
                ocr_file = str(saved["ocr_result.md"])
                if ocr_file not in doc_files:
                    doc_files.append(ocr_file)
            if doc_files:
                params["file"] = doc_files

        if not params.get("file"):
            if task in {"catalog", "checklist", "quiz", "knowledge_graph"}:
                params["file"] = None
            elif "ocr_result.md" in saved:
                params["file"] = [str(saved["ocr_result.md"])]
            elif saved:
                available = [str(p) for p in saved.values() if not str(p).lower().endswith((".png", ".jpg", ".jpeg"))]
                if available:
                    params["file"] = available
        elif task in {"catalog", "checklist", "quiz", "knowledge_graph"}:
            raw_f = params.get("file")
            if isinstance(raw_f, list) and len(raw_f) > 1:
                params["file"] = None

        # checklist 前置：plan 未显式包含 catalog 时才自动补跑（避免 catalog 跑两次 → v1+v2）
        if task == "checklist" and not (plan_tasks and "catalog" in plan_tasks):
            await self._run_catalog_prereq(params, task_id=task_id)

        res = await self._run_runner(task_id, task, params)
        ts_done = time.strftime("%H:%M:%S")
        state.setdefault("logs", []).append(f"[{ts_done}] 任务阶段 [{task_label}] 执行完成\n")
        return res

    async def _run_catalog_prereq(self, params: dict[str, Any], task_id: str = "") -> None:
        """checklist 执行前若该学科尚未建过目录，则自动跑 catalog（基于该学科知识库构建 v1）。"""
        state = self._tasks.get(task_id, {}) if task_id else {}
        user_id = str(params.get("user_id") or state.get("user_id") or "").strip()
        subject = str(params.get("subject") or "").strip()
        if not user_id or not subject:
            return  # 缺 user/subject 无法建目录，checklist 走已有目录

        # 1. 核心防护：若该学科已经存在知识目录，绝不再重复跑 catalog（避免重复生成并递增版本）
        try:
            from domain.notes.tasks.catalog.store import load_catalog

            if load_catalog(user_id=user_id, subject=subject) is not None:
                return
        except Exception:  # noqa: BLE001
            pass

        # 2. 该学科知识库为空 → 不建目录（避免 LLM 空跑）
        try:
            from tools.knowledge.cite import open_knowledge

            kb = open_knowledge(user_id=user_id)
            chunks = kb.list_chunks(user_id=user_id, subject=subject) if kb else []
        except Exception:  # noqa: BLE001
            return  # 知识库不可用也不建目录
        if not chunks:
            return
        import contextlib
        import io

        from chat.profile import resolve_user_profile_file
        from tools.core.profiles import SHARED_PROFILE_DIR
        from tools.core.runner import run
        from tools.runtime_context import load_domain

        ctx = load_domain("notes", self.root)
        profile = resolve_user_profile_file(self.root, user_id) if user_id else (SHARED_PROFILE_DIR / "object_profile.json")
        if not profile.exists():
            profile = ctx.default_profile_dir
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            await run(
                ctx,
                None,
                profile,
                self.root / ".env",
                tasks=["catalog"],
                user_id=user_id,
                subject=subject,
                monitor=False,
            )

    async def _run_ocr(self, task_id: str, params: dict[str, Any]) -> dict[str, Any]:
        import time
        from tools.ocr.levels.light import iter_ocr_review_pipeline
        from tools.ocr.mathmd import normalize_markdown_math

        inputs = params.get("input") or []
        if not inputs:
            raise ValueError("ocr 缺 input（图片路径）")
        state = self._tasks.get(task_id, {})
        workdir = Path(state.get("workdir") or (self.root / "data" / state.get("uid_safe", "default_user") / "uploads" / task_id))
        output_path = Path(str(params.get("output") or (workdir / "ocr_result.md")))

        def log_msg(msg: str):
            cur_time = time.strftime("%H:%M:%S")
            state.setdefault("logs", []).append(f"[{cur_time}] {msg}")

        image_entries = [(Path(p), Path(p).name) for p in inputs]
        total = len(image_entries)
        log_msg(f"准备识别图片共 {total} 张，启动并行 OCR 引擎...")

        batch_mds: list[str] = []
        batch_raws: list[str] = []

        def _worker_loop():
            for event in iter_ocr_review_pipeline(image_entries):
                kind = event.get("type")
                lo = event.get("lo")
                hi = event.get("hi")
                if kind == "ocr_start":
                    txt = f"正在识别第 {lo}–{hi} 张（并行 {event.get('workers')} 路，共 {total} 张）"
                    log_msg(txt)
                    state["message"] = txt
                    state["progress"] = min(88, int((lo - 1) / total * 70) + 15)
                elif kind == "ocr_item":
                    name = event.get("name")
                    done_chunk = event.get("done")
                    chunk_total = event.get("chunk")
                    txt = f"第 {lo}–{hi} 张识别进度 [{done_chunk}/{chunk_total}]：已完成「{name}」文字与公式识别"
                    log_msg(txt)
                    state["message"] = txt
                    overall_done = (lo - 1) + done_chunk
                    state["progress"] = min(85, int(overall_done / total * 70) + 15)
                elif kind == "ocr_fail":
                    name = event.get("name")
                    err = event.get("error") or "未知错误"
                    txt = f"第 {lo}–{hi} 张识别：图片「{name}」识别失败（{err}），已跳过"
                    log_msg(txt)
                    state["message"] = txt
                elif kind == "review_start":
                    txt = f"第 {lo}–{hi} 张识别完成，正在由模型整理排版并审校 LaTeX 公式…"
                    log_msg(txt)
                    state["message"] = txt
                elif kind == "batch_done":
                    batch_mds.append(str(event.get("reviewed") or ""))
                    batch_raws.append(str(event.get("raw") or ""))
                    log_msg(f"第 {lo}–{hi} 张批次整理审校完成")

        await asyncio.to_thread(_worker_loop)

        log_msg("各批次整理审校完成，正在按顺序拼接生成最终 Markdown 产物...")
        combined_reviewed = "\n\n".join(item for item in batch_mds if item.strip())
        combined_reviewed = normalize_markdown_math(combined_reviewed)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(combined_reviewed, encoding="utf-8")

        log_msg(f"OCR 识别完成，产物已落盘至: {output_path.name}（包含 {total} 张图片的公式与排版）")
        state["progress"] = 90
        state["message"] = f"OCR 识别完成，共成功识别 {total} 张图片"

        return {"task": "ocr", "ok": True, "output": str(output_path)}

    def _resolve_profile(self, label: str) -> dict[str, Any] | None:
        """按视角 label（如「职业 · 开发人员」）找对应 profile 数据。"""
        from tools.core.profiles import (
            SHARED_PROFILE_DIR,
            SHARED_ROLE_DIR,
            list_profile_entries,
        )

        for entry in (
            list_profile_entries(SHARED_PROFILE_DIR)
            + list_profile_entries(SHARED_ROLE_DIR)
        ):
            if entry.get("label") == label:
                return entry.get("data")
        return None

    async def _execute_runner_raw(
        self,
        task_id: str,
        task: str,
        params: dict[str, Any],
        file: list[Path] | None,
        profile: Path,
        ctx: Any,
    ) -> dict[str, Any]:
        import contextlib

        from tools.core.runner import run

        templates = None
        tpl = params.get("template")
        tpl_content = params.get("template_content")
        if tpl:
            tpl_src = tpl[0] if isinstance(tpl, list) else tpl
            if isinstance(tpl_src, str):
                p = Path(tpl_src)
                if not p.is_file():
                    domain = "notes" if task in {"library", "catalog", "checklist", "quiz", "knowledge_graph"} else "meeting"
                    candidates = [
                        self.root / "samples" / domain / f"{task}_template" / tpl_src,
                        self.root / "samples" / domain / "template" / tpl_src,
                        self.root / "template" / tpl_src,
                        self.root / tpl_src,
                    ]
                    for cand in candidates:
                        if cand.is_file():
                            p = cand
                            break
                if p.is_file():
                    templates = {task: p.resolve()}
        elif tpl_content and isinstance(tpl_content, str) and tpl_content.strip():
            scratch_tpl_dir = self.root / "scratch" / "templates"
            scratch_tpl_dir.mkdir(parents=True, exist_ok=True)
            import time

            scratch_tpl_path = scratch_tpl_dir / f"{task}_{int(time.time()*1000)}.md"
            scratch_tpl_path.write_text(tpl_content.strip(), encoding="utf-8")
            templates = {task: scratch_tpl_path.resolve()}

        state = self._tasks.get(task_id, {})
        out_stream = RealtimeLogStream(state)

        async def _periodic_flush() -> None:
            """LLM 流式输出可能长时间无换行，定时把累积文本刷入 logs，前端才看得到进度。"""
            try:
                while True:
                    await asyncio.sleep(2)
                    out_stream.flush()
            except asyncio.CancelledError:
                pass

        flush_handle = asyncio.create_task(_periodic_flush())
        try:
            with contextlib.redirect_stdout(out_stream):
                await run(
                    ctx,
                    file,
                    profile,
                    self.root / ".env",
                    templates,
                    tasks=[task],
                    user_id=params.get("user_id") or state.get("user_id") or None,
                    project_id=params.get("project") or None,
                    subject=params.get("subject") or None,
                    monitor=False,
                    stream_stdout=False,
                )
        finally:
            flush_handle.cancel()
            out_stream.flush()
        return {"task": task, "ok": True}

    async def _run_runner(self, task_id: str, task: str, params: dict[str, Any]) -> dict[str, Any]:
        state = self._tasks.get(task_id, {})
        from tools.runtime_context import load_domain
        from tools.core.runner import run
        from tools.profiles import SHARED_PROFILE_DIR

        domain = "notes" if task in {
            "library", "catalog", "checklist", "quiz", "knowledge_graph",
        } else "meeting"
        ctx = load_domain(domain, self.root)

        file = params.get("file") or params.get("input") or []
        if isinstance(file, str):
            file = [file]
        file = [Path(p) for p in file] if file else None

        user_id = str(params.get("user_id") or state.get("user_id") or "").strip()
        from chat.profile import resolve_user_profile_file, match_role_template, ROLE_TEMPLATE_MAP

        # 优先支持任务参数显式指定的视角/职业
        explicit_role = str(params.get("perspective") or params.get("role") or params.get("profile") or "").strip()
        if explicit_role:
            tpl_key, r_name, t_label = match_role_template(explicit_role)
            if tpl_key != "object":
                template_info = ROLE_TEMPLATE_MAP.get(tpl_key)
                if template_info:
                    p = SHARED_PROFILE_DIR / template_info["file"]
                    if p.is_file():
                        profile = p
                    else:
                        profile = resolve_user_profile_file(self.root, user_id) if user_id else (SHARED_PROFILE_DIR / "object_profile.json")
                else:
                    profile = resolve_user_profile_file(self.root, user_id) if user_id else (SHARED_PROFILE_DIR / "object_profile.json")
            else:
                profile = SHARED_PROFILE_DIR / "object_profile.json"
        elif user_id:
            profile = resolve_user_profile_file(self.root, user_id)
        else:
            profile = SHARED_PROFILE_DIR / "object_profile.json"
            if not profile.exists():
                profile = ctx.default_profile_dir

        # library：图片与文档支持并行处理 —— 常规文档直接先入库，图片并行跑 OCR 合成 md
        if file and task == "library":
            images = [p for p in file if p.suffix.lower() in IMAGE_EXTS]
            docs = [p for p in file if p.suffix.lower() not in IMAGE_EXTS]

            async def _ocr_images_task() -> Path | None:
                if not images:
                    return None
                self._log(
                    task_id,
                    f"[OCR] 检测到 {len(images)} 张笔记图片，正在并行调用 OCR 引擎进行文字与公式提取...",
                )
                from tools.ocr import ocr_image_to_markdown
                from tools.ocr.mathmd import normalize_markdown_math

                workdir = Path(state.get("workdir") or (self.root / "data" / state.get("uid_safe", "default_user") / "uploads" / task_id))
                out_md = workdir / f"ocr_{uuid.uuid4().hex[:8]}.md"

                def _ocr_all():
                    blocks = []
                    for idx, img_p in enumerate(images, 1):
                        self._log(
                            task_id,
                            f"[OCR] 正在识别第 [{idx}/{len(images)}] 张图片: 「{img_p.name}」...",
                        )
                        body = ocr_image_to_markdown(str(img_p), use_llm=False).strip()
                        if body:
                            blocks.append(f"<!-- Page {idx}: {img_p.name} -->\n" + body)
                    text = "\n\n---\n\n".join(blocks)
                    text = normalize_markdown_math(text)
                    out_md.parent.mkdir(parents=True, exist_ok=True)
                    out_md.write_text(text, encoding="utf-8")
                    return out_md

                res_md = await asyncio.to_thread(_ocr_all)
                self._log(
                    task_id,
                    f"[OCR] 批量识别完成！已成功合成排版笔记: 「{res_md.name}」（共 {len(images)} 页）",
                )
                return res_md

            async def _ingest_docs_task():
                if not docs:
                    return None
                self._log(
                    task_id,
                    f"[入库] 检测到 {len(docs)} 份常规文档（无需OCR），直接并行开始分块向量化入库...",
                )
                return await self._execute_runner_raw(task_id, task, params, docs, profile, ctx)

            # 1. 混合模式：常规文档直接入库 与 图片 OCR 并行执行
            if docs and images:
                ocr_future = asyncio.create_task(_ocr_images_task())
                docs_future = asyncio.create_task(_ingest_docs_task())
                await docs_future  # 文档并行秒级入库
                out_md = await ocr_future  # 等待图片 OCR 完成
                if out_md:
                    self._log(task_id, f"[入库] 正在将 OCR 合成的笔记 「{out_md.name}」 追加存入知识库...")
                    await self._execute_runner_raw(task_id, task, params, [out_md], profile, ctx)
                return {"task": task, "ok": True}

            # 2. 纯文档模式：直接入库
            if docs and not images:
                return await self._execute_runner_raw(task_id, task, params, docs, profile, ctx)

            # 3. 纯图片模式：OCR 完成后入库
            if images and not docs:
                out_md = await _ocr_images_task()
                if out_md:
                    return await self._execute_runner_raw(task_id, task, params, [out_md], profile, ctx)
                return {"task": task, "ok": True}

        return await self._execute_runner_raw(task_id, task, params, file, profile, ctx)
