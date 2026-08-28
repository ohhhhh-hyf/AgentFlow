"""任务监控组件：token 消耗 / 按层细分 / 延迟 / 重试失败 / 质量信号。

用法（runner 已自动接入；也可手动包裹任意一次 run_streaming）::

    from tools.monitor import TaskMonitor

    monitor = TaskMonitor(client, task_name="actions", meta={"domain": "meeting"})
    monitor.start(transcript=transcript)
    ...  # 运行任务，拿到 done 事件
    payload = monitor.finish(done_event=done_event)   # 落盘 output/monitor/*.json
"""
from .monitor import DEFAULT_OUT_DIR, TaskMonitor
from .side import (
    record_knowledge_ingest,
    record_knowledge_search,
    record_memory_persist,
    record_memory_prepare,
    snapshot as side_snapshot,
)

__all__ = [
    "DEFAULT_OUT_DIR",
    "TaskMonitor",
    "record_knowledge_ingest",
    "record_knowledge_search",
    "record_memory_persist",
    "record_memory_prepare",
    "side_snapshot",
]
