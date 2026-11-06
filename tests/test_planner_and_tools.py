import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from planner import build_schedule
from storage import Store
from tools import Toolkit

TODAY = date(2026, 11, 1)


def task(i, title, due, est, prio=2, done=0.0, status="pending", subject="X"):
    return {"id": i, "title": title, "subject": subject, "due_date": due,
            "est_hours": est, "done_hours": done, "priority": prio, "status": status}


@pytest.fixture
def kit(tmp_path):
    return Toolkit(store=Store(tmp_path / "state.json"), today=TODAY)


# ---------------- planner ----------------
def test_schedules_everything_before_deadline():
    tasks = [task(1, "A", "2026-11-03", 4), task(2, "B", "2026-11-05", 4)]
    r = build_schedule(tasks, TODAY, 7, daily_hours=4, max_block=2)
    scheduled = {}
    for d in r["days"]:
        for s in d["sessions"]:
            assert d["date"] <= tasks[s["task_id"] - 1]["due_date"]
            scheduled[s["task_id"]] = scheduled.get(s["task_id"], 0) + s["hours"]
    assert scheduled == {1: 4, 2: 4}
    assert r["at_risk"] == []


def test_daily_capacity_respected():
    tasks = [task(1, "A", "2026-11-10", 20)]
    r = build_schedule(tasks, TODAY, 10, daily_hours=3, max_block=2)
    assert all(d["total_hours"] <= 3 for d in r["days"])


def test_blocked_days_get_no_sessions():
    tasks = [task(1, "A", "2026-11-04", 6)]
    r = build_schedule(tasks, TODAY, 5, 3, 2, blocked={"2026-11-02": "trip"})
    day = next(d for d in r["days"] if d["date"] == "2026-11-02")
    assert day["sessions"] == [] and day["blocked"]


def test_at_risk_flagged_when_impossible():
    tasks = [task(1, "Big", "2026-11-02", 10)]  # only 2 days x 3h = 6h
    r = build_schedule(tasks, TODAY, 5, 3, 2)
    assert r["at_risk"][0]["task_id"] == 1
    assert r["at_risk"][0]["unscheduled_hours"] == 4


def test_urgent_task_gets_first_slot_and_subjects_interleave():
    tasks = [task(1, "Later", "2026-11-09", 8), task(2, "Soon", "2026-11-03", 4)]
    r = build_schedule(tasks, TODAY, 9, 4, 2)
    first = r["days"][0]["sessions"]
    assert {s["task_id"] for s in first} == {1, 2}  # interleaved
    assert first[0]["task_id"] == 2                  # urgent listed first


def test_done_tasks_ignored_and_progress_counted():
    tasks = [task(1, "A", "2026-11-05", 4, status="done"),
             task(2, "B", "2026-11-05", 4, done=3)]
    r = build_schedule(tasks, TODAY, 5, 4, 2)
    total = sum(s["hours"] for d in r["days"] for s in d["sessions"])
    assert total == 1


def test_overdue_task_is_scheduled_and_reported():
    tasks = [task(1, "Late", "2026-10-30", 2)]
    r = build_schedule(tasks, TODAY, 3, 4, 2)
    assert r["overdue"] == [1]
    assert r["days"][0]["sessions"][0]["task_id"] == 1


# ---------------- tools ----------------
def test_add_list_progress_delete(kit):
    out = kit.add_task("HT assignment", "Heat Transfer", "2026-11-09", 5, 3)
    tid = out["added"]["id"]
    assert kit.list_tasks("pending")["count"] == 1
    kit.log_progress(tid, 2)
    assert kit.list_tasks()["tasks"][0]["done_hours"] == 2
    res = kit.log_progress(tid, 3)
    assert res["task"]["status"] == "done" and res["hours_remaining"] == 0
    assert kit.list_tasks("pending")["count"] == 0
    kit.delete_task(tid)
    assert kit.list_tasks()["count"] == 0


def test_bad_input_returns_error_not_exception(kit):
    assert "error" in kit.call("add_task", {"title": "x", "subject": "y",
                                            "due_date": "tomorrow", "est_hours": 2})
    assert "error" in kit.call("add_task", {"title": "x", "subject": "y",
                                            "due_date": "2026-11-09", "est_hours": -1})
    assert "error" in kit.call("log_progress", {"task_id": 99, "hours_done": 1})
    assert "error" in kit.call("no_such_tool", {})
    assert "error" in kit.call("add_task", {"wrong_arg": 1})


def test_generate_schedule_and_day_lookup(kit):
    kit.add_task("A", "S", "2026-11-04", 4)
    kit.block_date("2026-11-02", "trip")
    kit.set_daily_hours(3)
    res = kit.generate_schedule("", 5)
    assert res["at_risk"] == []
    assert kit.get_plan_for_day("2026-11-02")["sessions"] == []
    assert kit.get_plan_for_day("2026-11-03")["sessions"]
    assert kit.get_current_date() == {"today": "2026-11-01", "weekday": "Sunday"}


def test_state_persists_between_toolkits(tmp_path):
    path = tmp_path / "s.json"
    Toolkit(Store(path), TODAY).add_task("A", "S", "2026-11-09", 2)
    assert Toolkit(Store(path), TODAY).list_tasks()["count"] == 1


def test_read_text_file_is_sandboxed(kit, monkeypatch):
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(repo)
    ok = kit.call("read_text_file", {"filename": "sample_syllabus.txt"})
    assert "Heat Transfer" in ok["content"]
    assert "error" in kit.call("read_text_file", {"filename": "../../etc/passwd"})
    assert "error" in kit.call("read_text_file", {"filename": "missing.txt"})
