# -*- coding: utf-8 -*-
"""backend 执行器 —— 按 Plan 分组执行任务（复用现有 runner / tools.ocr）。

- 依赖组串行、无依赖组并行（asyncio.gather）
- 上传文件落盘 data/uploads/{task_id}/，映射进任务 params（file/input）
- 状态记录：running → done / failed，含当前任务与产物清单
"""
from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile


class TaskRunner:
    def __init__(self, root: Path, uploads_dir: Path) -> None:
        self.root = root
        self.uploads_dir = uploads_dir
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

    # ── 提交 ──
    def submit(self, plan: dict[str, Any], files: list[UploadFile]) -> str:
        task_id = uuid.uuid4().hex[:10]
        workdir = self.uploads_dir / task_id
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
            "plan": plan,
            "saved": {k: str(v) for k, v in saved.items()},
            "logs": [],
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
        saved = {k: Path(v) for k, v in state.get("saved", {}).items()}
        entries = plan.get("plan") or []
        groups: list[list[dict[str, Any]]] = plan.get("execution") or [[e] for e in entries]

        state["status"] = "running"
        by_task = {str(e.get("task")): e for e in entries}
        try:
            for group in groups:
                async def _one(entry: dict[str, Any]) -> dict[str, Any]:
                    state["current"] = f"{entry.get('task')}"
                    try:
                        return await self._run_one(task_id, entry, saved)
                    except Exception as exc:  # noqa: BLE001
                        import traceback

                        tb = traceback.format_exc()
                        return {"task": entry.get("task"), "ok": False, "error": tb[-1200:]}

                group_entries = [by_task[str(name)] for name in group if str(name) in by_task]
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
            state["status"] = "done"
            state["message"] = "全部任务完成"
        except Exception as exc:  # noqa: BLE001
            state["status"] = "failed"
            state["message"] = str(exc)
        state["current"] = ""

    async def _run_one(
        self,
        task_id: str,
        entry: dict[str, Any],
        saved: dict[str, Path],
    ) -> dict[str, Any]:
        task = str(entry.get("task") or "")
        params = dict(entry.get("params") or {})
        # 把上传文件映射进 file/input 参数
        for key in ("file", "input"):
            vals = params.get(key)
            if isinstance(vals, list) and vals:
                resolved = []
                for v in vals:
                    if v in saved:
                        resolved.append(str(saved[v]))
                    else:
                        resolved.append(str(v))
                params[key] = resolved
        if task == "ocr":
            return await self._run_ocr(params)
        return await self._run_runner(task_id, task, params)

    async def _run_ocr(self, params: dict[str, Any]) -> dict[str, Any]:
        inputs = params.get("input") or []
        if not inputs:
            raise ValueError("ocr 缺 input（图片路径）")
        output = str(params.get("output") or "").strip()
        from tools.ocr import ocr_images_to_markdown

        result = await asyncio.to_thread(
            ocr_images_to_markdown, inputs, output or None, True
        )
        return {"task": "ocr", "ok": True, "output": (result or "")[:200]}

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

    async def _run_runner(self, task_id: str, task: str, params: dict[str, Any]) -> dict[str, Any]:
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

        profile = SHARED_PROFILE_DIR / "object_profile.json"
        if not profile.exists():
            profile = ctx.default_profile_dir

        # 视角选择：params.perspective（如「职业 · 开发人员」）→ 对应 profile JSON
        perspective_label = str(params.get("perspective") or "").strip()
        if perspective_label:
            resolved = self._resolve_profile(perspective_label)
            if resolved is not None:
                import tempfile

                tmp = tempfile.NamedTemporaryFile(
                    "w", suffix=".json", delete=False, encoding="utf-8"
                )
                tmp.write(json.dumps(resolved, ensure_ascii=False, indent=2))
                tmp.close()
                profile = Path(tmp.name)

        # runner 流式输出写 sys.stdout.flush()，uvicorn 进程的管道会 OSError 22；
        # 重定向到内存 buffer，产物照常落盘，日志留作排查。
        import contextlib
        import io

        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            await run(
                ctx,
                file,
                profile,
                self.root / ".env",
                tasks=[task],
                user_id=params.get("user_id") or None,
                project_id=params.get("project") or None,
                subject=params.get("subject") or None,
                monitor=False,
            )
        logs = (out_buf.getvalue() or "").strip().splitlines()
        state = self._tasks.get(task_id)
        if state is not None:
            state.setdefault("logs", []).extend(logs[-50:])
        return {"task": task, "ok": True}
