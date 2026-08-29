"""任务监控组件（tools.monitor）。

对一个任务运行（一次 run_streaming）做整体监控：

- **token 消耗**：读 ``LLMClient.monitor_snapshot()``，用「基线差值法」计算
  本次任务实际消耗（prompt / completion / total / calls / cache_hits）
- **按层细分**：``usage_by_label``（core 理解 / 各线 agent / supervisor / render）
- **延迟**：``latency_by_label``（总耗时 / 均值 / 最大值）
- **健壮性**：重试次数 / 失败次数
- **质量信号**：done 事件的 quality_warning / gate_by_line / 各线输出规模

数据落盘到 ``data/monitor/{task}_{timestamp}.json``，不记录任何输入正文内容。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 项目根（tools/monitor/monitor.py → 上两级）
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT / "data" / "monitor"


class TaskMonitor:
    """一次任务运行的生命周期监控（start → 运行 → finish）。

    用法::

        monitor = TaskMonitor(client, task_name="actions", meta={"domain": "meeting"})
        monitor.start(transcript=transcript)
        ...  # 运行 run_streaming
        monitor.finish(done_event=done_event)   # 返回 dict 并落盘 JSON

    容错：client 缺失或旧版（无 monitor_snapshot）时降级为只读 usage_totals；
    任何异常不影响主流程（调用方应 try/except）。
    """

    def __init__(
        self,
        client: Any = None,
        task_name: str = "",
        meta: dict | None = None,
        out_dir: str | Path | None = None,
    ) -> None:
        self.client = client
        self.task_name = task_name or "task"
        self.meta: dict = dict(meta or {})
        self.out_dir = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
        # 运行期状态
        self._base: dict = {}
        self._side_base: dict = {}
        self._started_at: str = ""
        self._start_wall: float = 0.0
        self._input_chars: int = 0
        self._input_lines: int = 0
        self._finished: bool = False

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self, transcript: str = "", extra: dict | None = None) -> None:
        """任务开始：记录监控基线（token 差值法的起点）与输入规模。"""
        self._input_chars = len(transcript or "")
        self._input_lines = (transcript or "").count("\n") + 1
        self._started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._start_wall = time.monotonic()
        self._base = self._client_snapshot()
        self._side_base = self._side_snapshot()
        self._finished = False
        if extra:
            self.meta.update(extra)

    def finish(self, done_event: dict | None = None, extra: dict | None = None) -> dict:
        """任务结束：汇总监控数据并落盘，返回完整 payload（幂等）。"""
        if self._finished:
            return self._last_payload
        snap = self._client_snapshot()
        payload = self._build_payload(snap, done_event)
        if extra:
            extra_meta = {
                key: value
                for key, value in extra.items()
                if key not in {"ok", "error"}
            }
            if extra_meta:
                payload.setdefault("meta", {}).update(extra_meta)
            if "ok" in extra:
                payload["ok"] = bool(extra["ok"])
            if extra.get("error"):
                payload["error"] = str(extra["error"])
                payload["ok"] = False
            payload["scope"] = {
                "user_id": str(payload.get("meta", {}).get("user_id") or ""),
                "subject": str(payload.get("meta", {}).get("subject") or ""),
            }
        self._last_payload = payload
        self._finished = True
        path = self._persist(payload)
        payload["path"] = str(path)
        logger.info(
            "任务监控完成 task=%s total_tokens=%s calls=%s 耗时=%.1fs 文件=%s",
            self.task_name,
            payload["usage"].get("total_tokens", 0),
            payload["usage"].get("calls", 0),
            payload.get("duration_seconds", 0.0),
            path,
        )
        return payload

    # ── 数据采集 ──────────────────────────────────────────────

    def _client_snapshot(self) -> dict:
        """读 client 监控快照；旧版 client 降级为只读 usage_totals。"""
        if self.client is None:
            return {}
        snap = getattr(self.client, "monitor_snapshot", None)
        if callable(snap):
            try:
                return snap() or {}
            except Exception:  # noqa: BLE001 - 监控失败不阻断
                logger.warning("client.monitor_snapshot 失败，降级读取 usage_totals", exc_info=True)
        totals = dict(getattr(self.client, "usage_totals", None) or {})
        return {"usage_totals": totals}

    @staticmethod
    def _side_snapshot() -> dict:
        try:
            from tools.monitor.side import snapshot

            return snapshot()
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def _diff_value(base: dict, now: dict, key: str, default: int = 0) -> int:
        return int(now.get(key, default)) - int(base.get(key, default))

    def _diff_snapshot(self, snap: dict) -> dict:
        """基线差值：本次任务期间新增的监控数据。"""
        base = self._base
        base_totals = base.get("usage_totals") or {}
        now_totals = snap.get("usage_totals") or {}
        usage = {
            key: self._diff_value(base_totals, now_totals, key)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "calls", "cache_hits", "cache_hit_tokens")
        }

        base_labels = base.get("usage_by_label") or {}
        now_labels = snap.get("usage_by_label") or {}
        usage_by_label: dict[str, dict] = {}
        for label in set(base_labels) | set(now_labels):
            b = base_labels.get(label) or {}
            n = now_labels.get(label) or {}
            usage_by_label[label] = {
                key: self._diff_value(b, n, key)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens", "calls", "cache_hits", "cache_hit_tokens")
            }
        # 去掉空槽（无调用也无消耗）
        usage_by_label = {k: v for k, v in usage_by_label.items() if v.get("calls") or v.get("total_tokens")}

        base_lat = base.get("latency_by_label") or {}
        now_lat = snap.get("latency_by_label") or {}
        latency_by_label: dict[str, dict] = {}
        for label in set(base_lat) | set(now_lat):
            b = base_lat.get(label) or {}
            n = now_lat.get(label) or {}
            calls = self._diff_value(b, n, "calls")
            if calls <= 0:
                continue
            latency_by_label[label] = {
                "calls": calls,
                "total_seconds": round(
                    float(n.get("total_seconds", 0.0)) - float(b.get("total_seconds", 0.0)), 3
                ),
                "avg_seconds": 0.0,
                "max_seconds": round(float(n.get("max_seconds", 0.0)), 3),
            }
            latency_by_label[label]["avg_seconds"] = round(
                latency_by_label[label]["total_seconds"] / calls, 3
            )

        return {
            "usage": usage,
            "usage_by_label": usage_by_label,
            "latency_by_label": latency_by_label,
            "retries": self._diff_value(base, snap, "retries_total"),
            "failures": self._diff_value(base, snap, "failures_total"),
        }

    # ── 组装与落盘 ────────────────────────────────────────────

    def _collect_output(self, done_event: dict | None) -> dict:
        """从 done 事件提取各线输出规模（条数 + 文本长度），不保存正文。"""
        out: dict[str, dict] = {}
        if not done_event:
            return out
        reports = done_event.get("reports") or {}
        for line_name, report in reports.items():
            data = report
            if hasattr(data, "model_dump"):
                try:
                    data = data.model_dump()
                except Exception:  # noqa: BLE001
                    data = {}
            if not isinstance(data, dict):
                data = {}
            list_items = 0
            text_chars = 0
            for value in data.values():
                if isinstance(value, list):
                    list_items += len(value)
                elif isinstance(value, str):
                    text_chars += len(value)
            out[str(line_name)] = {"items": list_items, "text_chars": text_chars}
        return out

    def _build_payload(self, snap: dict, done_event: dict | None) -> dict:
        diff = self._diff_snapshot(snap)
        duration = time.monotonic() - self._start_wall if self._start_wall else 0.0
        event = done_event or {}
        pipeline = event.get("pipeline") if isinstance(event.get("pipeline"), dict) else {}
        any_fallback = any(
            isinstance(row, dict) and row.get("fallback") for row in pipeline.values()
        )
        try:
            from tools.monitor.side import diff_side, split_side

            knowledge, memory = split_side(diff_side(self._side_base, self._side_snapshot()))
        except Exception:  # noqa: BLE001
            knowledge, memory = {}, {}
        return {
            "task": self.task_name,
            "meta": dict(self.meta),
            "started_at": self._started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(duration, 3),
            "ok": bool(done_event),
            "error": "",
            "scope": {
                "user_id": str(self.meta.get("user_id") or ""),
                "subject": str(self.meta.get("subject") or ""),
            },
            "input": {
                "transcript_chars": self._input_chars,
                "transcript_lines": self._input_lines,
            },
            "usage": diff["usage"],
            "usage_by_label": diff["usage_by_label"],
            "latency_by_label": diff["latency_by_label"],
            "retries": diff["retries"],
            "failures": diff["failures"],
            "output": self._collect_output(done_event),
            "pipeline": pipeline,
            "knowledge": knowledge,
            "memory": memory,
            "quality": {
                "warning": event.get("quality_warning"),
                "gate_by_line": event.get("gate_by_line") or {},
                "fallback": any_fallback,
            },
        }

    def _persist(self, payload: dict) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_task = "".join(ch for ch in self.task_name if ch.isalnum() or ch in "+-_") or "task"
        path = self.out_dir / f"{safe_task}_{ts}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


__all__ = ["TaskMonitor", "DEFAULT_OUT_DIR"]
