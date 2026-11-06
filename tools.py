"""Tools the agent can call.

Every public method of Toolkit is exposed to the LLM. The docstrings and type
hints ARE the tool schema the model sees, so keep them accurate.
Methods never raise for bad input: they return {"error": "..."} so the agent
can read the message and correct itself.
"""
from datetime import date
from pathlib import Path

from planner import build_schedule
from storage import Store

INPUT_DIR = Path("data/inputs")
MAX_FILE_CHARS = 20000


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{value}' is not a valid date; use YYYY-MM-DD")


class Toolkit:
    def __init__(self, store=None, today=None):
        self.store = store or Store()
        self._today = today  # injectable for tests

    # ---- helpers (underscore methods are NOT exposed to the model) ----
    def _now(self):
        return self._today or date.today()

    def _find(self, state, task_id):
        for t in state["tasks"]:
            if t["id"] == task_id:
                return t
        raise ValueError(f"No task with id {task_id}")

    @property
    def tools(self):
        """Bound methods handed to the LLM as callable tools."""
        return [
            self.get_current_date,
            self.add_task,
            self.list_tasks,
            self.log_progress,
            self.delete_task,
            self.set_daily_hours,
            self.block_date,
            self.generate_schedule,
            self.get_plan_for_day,
            self.read_text_file,
        ]

    def call(self, name, args):
        """Dispatch a tool call requested by the model."""
        fn = {f.__name__: f for f in self.tools}.get(name)
        if fn is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return fn(**(args or {}))
        except (ValueError, TypeError) as e:
            return {"error": str(e)}

    # ---- tools ----
    def get_current_date(self) -> dict:
        """Get today's date and weekday. Call this first whenever the user uses
        relative dates such as 'tomorrow', 'next Friday' or 'in two weeks'."""
        d = self._now()
        return {"today": d.isoformat(), "weekday": d.strftime("%A")}

    def add_task(self, title: str, subject: str, due_date: str,
                 est_hours: float, priority: int = 2) -> dict:
        """Add a study task, assignment or exam-prep item to the planner.

        Args:
            title: Short name of the task, e.g. 'Heat Transfer assignment 3'.
            subject: Course or subject the task belongs to.
            due_date: Deadline in YYYY-MM-DD format.
            est_hours: Estimated total hours of work needed (greater than 0).
            priority: 1 (low), 2 (normal) or 3 (high). Breaks ties between same-deadline tasks.
        """
        due = _parse_date(due_date)
        if est_hours <= 0:
            raise ValueError("est_hours must be greater than 0")
        if priority not in (1, 2, 3):
            raise ValueError("priority must be 1, 2 or 3")
        state = self.store.load()
        task = {
            "id": state["next_id"],
            "title": title,
            "subject": subject,
            "due_date": due.isoformat(),
            "est_hours": float(est_hours),
            "done_hours": 0.0,
            "priority": int(priority),
            "status": "pending",
        }
        state["next_id"] += 1
        state["tasks"].append(task)
        self.store.save(state)
        return {"added": task}

    def list_tasks(self, status: str = "all") -> dict:
        """List tasks in the planner, sorted by deadline.

        Args:
            status: 'all', 'pending' or 'done'.
        """
        if status not in ("all", "pending", "done"):
            raise ValueError("status must be 'all', 'pending' or 'done'")
        tasks = self.store.load()["tasks"]
        if status != "all":
            tasks = [t for t in tasks if t["status"] == status]
        tasks = sorted(tasks, key=lambda t: (t["due_date"], -t["priority"]))
        return {"count": len(tasks), "tasks": tasks}

    def log_progress(self, task_id: int, hours_done: float) -> dict:
        """Record hours the student has just spent on a task. The task is marked
        done automatically once its estimate is reached.

        Args:
            task_id: Id of the task (from list_tasks).
            hours_done: Hours completed in this session (greater than 0).
        """
        if hours_done <= 0:
            raise ValueError("hours_done must be greater than 0")
        state = self.store.load()
        task = self._find(state, task_id)
        task["done_hours"] = round(task["done_hours"] + hours_done, 2)
        if task["done_hours"] >= task["est_hours"]:
            task["status"] = "done"
        self.store.save(state)
        left = max(task["est_hours"] - task["done_hours"], 0)
        return {"task": task, "hours_remaining": round(left, 2)}

    def delete_task(self, task_id: int) -> dict:
        """Permanently remove a task from the planner.

        Args:
            task_id: Id of the task to delete.
        """
        state = self.store.load()
        task = self._find(state, task_id)
        state["tasks"].remove(task)
        self.store.save(state)
        return {"deleted": task["title"]}

    def set_daily_hours(self, hours: float) -> dict:
        """Set how many hours per day the student can study.

        Args:
            hours: Hours per day, between 0.5 and 16.
        """
        if not 0.5 <= hours <= 16:
            raise ValueError("hours must be between 0.5 and 16")
        state = self.store.load()
        state["settings"]["daily_hours"] = float(hours)
        self.store.save(state)
        return {"daily_hours": hours}

    def block_date(self, date: str, reason: str = "") -> dict:
        """Mark a date as unavailable for studying (travel, festival, event).

        Args:
            date: Date in YYYY-MM-DD format.
            reason: Optional reason, e.g. 'family function'.
        """
        d = _parse_date(date)
        state = self.store.load()
        state["blocked_dates"][d.isoformat()] = reason
        self.store.save(state)
        return {"blocked": d.isoformat(), "reason": reason}

    def generate_schedule(self, start_date: str = "", days: int = 14) -> dict:
        """Build a day-by-day study schedule for all pending tasks using the
        planner algorithm, save it, and report tasks at risk of missing their
        deadline. Call again after any change to tasks, hours or blocked dates.

        Args:
            start_date: First day, YYYY-MM-DD. Empty string means today.
            days: Number of days to plan, 1 to 60.
        """
        if not 1 <= days <= 60:
            raise ValueError("days must be between 1 and 60")
        start = _parse_date(start_date) if start_date else self._now()
        state = self.store.load()
        result = build_schedule(
            state["tasks"], start, days,
            state["settings"]["daily_hours"],
            state["settings"]["max_block_hours"],
            state["blocked_dates"],
        )
        state["schedule"] = result["days"]
        self.store.save(state)
        busy = [d for d in result["days"] if d["sessions"]]
        return {
            "planned_days": len(result["days"]),
            "days_with_study": len(busy),
            "at_risk": result["at_risk"],
            "overdue_task_ids": result["overdue"],
            "preview": busy[:7],
        }

    def get_plan_for_day(self, date: str = "") -> dict:
        """Get the saved study plan for one day.

        Args:
            date: Date in YYYY-MM-DD format. Empty string means today.
        """
        d = _parse_date(date) if date else self._now()
        for day in self.store.load()["schedule"]:
            if day["date"] == d.isoformat():
                return day
        return {"date": d.isoformat(), "sessions": [],
                "note": "No saved plan for this day. Run generate_schedule first."}

    def read_text_file(self, filename: str) -> dict:
        """Read a text file (e.g. a syllabus or deadline list) from the
        data/inputs folder so tasks can be extracted from it.

        Args:
            filename: File name inside data/inputs, e.g. 'syllabus.txt'.
        """
        path = (INPUT_DIR / filename).resolve()
        if INPUT_DIR.resolve() not in path.parents:
            raise ValueError("Only files inside data/inputs can be read")
        if not path.is_file():
            names = sorted(p.name for p in INPUT_DIR.glob("*")) if INPUT_DIR.exists() else []
            return {"error": f"File not found. Available files: {names}"}
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"filename": filename, "truncated": len(text) > MAX_FILE_CHARS,
                "content": text[:MAX_FILE_CHARS]}
