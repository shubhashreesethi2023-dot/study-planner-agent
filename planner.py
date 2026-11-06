"""Deterministic scheduling algorithm (no LLM involved).

Strategy: earliest-deadline-first with priority tie-breaking. Each day's
capacity is handed out in rotating chunks (max_block hours) so several
subjects are interleaved instead of one task hogging a whole day.
"""
from datetime import date, timedelta

EPS = 1e-9


def _round_q(hours):
    """Round to the nearest quarter hour."""
    return round(hours * 4) / 4


def build_schedule(tasks, start, horizon_days, daily_hours, max_block, blocked=None):
    """Return {"days": [...], "at_risk": [...], "overdue": [...]}.

    tasks: list of task dicts (id, title, subject, due_date, est_hours,
           done_hours, priority, status)
    start: datetime.date, first day of the plan
    blocked: set/dict of ISO dates with zero capacity
    """
    blocked = blocked or {}
    by_id = {t["id"]: t for t in tasks}
    remaining = {}
    for t in tasks:
        if t["status"] == "done":
            continue
        left = t["est_hours"] - t["done_hours"]
        if left > EPS:
            remaining[t["id"]] = left

    order = sorted(
        remaining,
        key=lambda i: (by_id[i]["due_date"], -by_id[i]["priority"], i),
    )
    overdue = [i for i in order if date.fromisoformat(by_id[i]["due_date"]) < start]

    days = []
    for offset in range(horizon_days):
        day = start + timedelta(days=offset)
        iso = day.isoformat()
        capacity = 0.0 if iso in blocked else float(daily_hours)
        per_task = {}

        progressed = True
        while capacity > EPS and progressed:
            progressed = False
            for tid in order:
                if capacity <= EPS:
                    break
                if remaining[tid] <= EPS:
                    continue
                due = date.fromisoformat(by_id[tid]["due_date"])
                # eligible if due on/after today, or already overdue (catch-up)
                if due < day and due >= start:
                    continue
                chunk = min(max_block, remaining[tid], capacity)
                remaining[tid] -= chunk
                capacity -= chunk
                per_task[tid] = per_task.get(tid, 0.0) + chunk
                progressed = True

        sessions = [
            {
                "task_id": tid,
                "title": by_id[tid]["title"],
                "subject": by_id[tid]["subject"],
                "hours": _round_q(h),
            }
            for tid, h in per_task.items()
        ]
        days.append(
            {
                "date": iso,
                "weekday": day.strftime("%A"),
                "blocked": iso in blocked,
                "total_hours": _round_q(sum(s["hours"] for s in sessions)),
                "sessions": sessions,
            }
        )

    end = start + timedelta(days=horizon_days - 1)
    at_risk = []
    for tid in order:
        if remaining[tid] > 0.05:
            due = date.fromisoformat(by_id[tid]["due_date"])
            if due <= end:  # deadline falls inside the planned window
                at_risk.append(
                    {
                        "task_id": tid,
                        "title": by_id[tid]["title"],
                        "due_date": by_id[tid]["due_date"],
                        "unscheduled_hours": _round_q(remaining[tid]),
                    }
                )
    return {"days": days, "at_risk": at_risk, "overdue": overdue}
