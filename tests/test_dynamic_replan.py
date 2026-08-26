# -*- coding: utf-8 -*-
from pathlib import Path

from backend.executor import TaskRunner


def test_supervisor_inserts_catalog_before_checklist(tmp_path):
    runner = TaskRunner(root=tmp_path)
    task_id = "task1"
    plan = {
        "plan": [
            {
                "task": "library",
                "domain": "notes",
                "params": {"user_id": "u1", "subject": "物理"},
                "missing": [],
                "needs": [],
            },
            {
                "task": "checklist",
                "domain": "notes",
                "params": {"user_id": "u1", "subject": "物理"},
                "missing": [],
                "needs": ["library"],
            },
        ],
        "execution": [["library"], ["checklist"]],
    }
    runner._tasks[task_id] = {"logs": [], "user_id": "u1"}

    runner._observe_and_replan(
        task_id,
        runner._tasks[task_id],
        plan,
        [{"task": "library", "ok": True}],
    )

    tasks = [item["task"] for item in plan["plan"]]
    assert tasks == ["library", "catalog", "checklist"]
    assert plan["execution"] == [["library"], ["catalog"], ["checklist"]]
    assert plan["plan"][1]["dynamic"] is True
    assert runner._tasks[task_id]["plan_updated"] is True
    assert runner._tasks[task_id]["replan_events"][0]["task"] == "catalog"


def test_supervisor_does_not_insert_catalog_without_scope(tmp_path):
    runner = TaskRunner(root=tmp_path)
    task_id = "task2"
    plan = {
        "plan": [
            {
                "task": "library",
                "domain": "notes",
                "params": {},
                "missing": [],
                "needs": [],
            },
            {
                "task": "checklist",
                "domain": "notes",
                "params": {},
                "missing": ["user_id", "subject"],
                "needs": ["library"],
            },
        ],
        "execution": [["library"], ["checklist"]],
    }
    runner._tasks[task_id] = {"logs": []}

    runner._observe_and_replan(
        task_id,
        runner._tasks[task_id],
        plan,
        [{"task": "library", "ok": True}],
    )

    assert [item["task"] for item in plan["plan"]] == ["library", "checklist"]
    assert not runner._tasks[task_id].get("plan_updated")
