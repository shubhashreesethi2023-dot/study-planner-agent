# Study Planner Agent

An autonomous AI agent that turns a student's goals ("I have a thermodynamics exam on 20 Nov, plan my week") into a concrete, adaptive study schedule. It is built on **Google Gemini function calling** and runs a visible **Think → Act → Observe** loop: the model decides which tool to call, the code executes it, and the result is fed back until the goal is met.

## What makes it an agent (not just a chatbot)

|Agent property|How it is implemented|
|-|-|
|Goal-driven|Takes a high-level request and decides the steps itself|
|Tool use|10 tools that read and change real state (tasks, availability, schedule)|
|Multi-step reasoning|Loops up to 12 rounds per request (`run\\\\\\\_turn` in `agent.py`)|
|Observation and self-correction|Tool errors come back as `{"error": ...}` and the model retries with fixed input|
|Memory|Conversation history in-session; tasks, settings and schedule persist in `data/state.json`|
|Safety limits|Step cap, file-read sandbox (`data/inputs` only), input validation on every tool|
|Reliable planning|Scheduling is deterministic code (`planner.py`), not LLM guesswork|

## Architecture / schema

!\[Architecture](docs/architecture.png)

Editable source: [`docs/architecture.svg`](docs/architecture.svg). Machine-readable tool schema (what the LLM sees): [`docs/tools\\\\\\\_schema.json`](docs/tools_schema.json).

```mermaid
sequenceDiagram
    participant S as Student
    participant A as agent.py (loop)
    participant G as Gemini LLM
    participant T as Toolkit (tools.py)
    participant D as state.json
    S->>A: "Plan my exam prep, due 2026-11-20, 12h"
    loop until no more tool calls (max 12)
        A->>G: conversation + tool schemas
        G-->>A: function\\\\\\\_call(name, args)
        A->>T: call(name, args)
        T->>D: read / write
        T-->>A: result or {"error"}
        A->>G: function\\\\\\\_response
    end
    G-->>A: final answer
    A-->>S: schedule + risk warnings
```

### Tools

|Tool|Purpose|
|-|-|
|`get\\\\\\\_current\\\\\\\_date`|Resolve "tomorrow", "next Friday"|
|`add\\\\\\\_task`|Add an assignment / exam-prep item (title, subject, due date, hours, priority)|
|`list\\\\\\\_tasks`|View tasks by status|
|`log\\\\\\\_progress`|Record hours studied; auto-completes tasks|
|`delete\\\\\\\_task`|Remove a task|
|`set\\\\\\\_daily\\\\\\\_hours`|Set daily study capacity|
|`block\\\\\\\_date`|Mark a day unavailable|
|`generate\\\\\\\_schedule`|Build the day-by-day plan and flag at-risk tasks|
|`get\\\\\\\_plan\\\\\\\_for\\\\\\\_day`|Show one day's saved plan|
|`read\\\\\\\_text\\\\\\\_file`|Read a syllabus / deadline list from `data/inputs`|

### Scheduling algorithm

Earliest-deadline-first with priority tie-breaking. Each day's capacity is handed out in rotating 2-hour chunks, so subjects are interleaved. Tasks that cannot fit before their deadline are reported as `at\\\\\\\_risk` with the missing hours, and the agent suggests fixes.

## Setup

```bash
git clone <your-repo-url>
cd study-planner-agent
python -m venv .venv \\\\\\\&\\\\\\\& source .venv/bin/activate    # Windows: .venv\\\\\\\\Scripts\\\\\\\\activate
pip install -r requirements.txt
cp .env.example .env        # then paste your key into .env
```

Get a free Gemini API key at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey).

## Run

```bash
python agent.py              # interactive chat
python agent.py --verbose    # show full tool results
python agent.py --reset      # clear saved data first
```

Example session:

```
you> Read sample\\\\\\\_syllabus.txt and add all my tasks. I can study 3 hours a day.
  -> \\\\\\\[1] read\\\\\\\_text\\\\\\\_file({"filename": "sample\\\\\\\_syllabus.txt"})
  -> \\\\\\\[2] add\\\\\\\_task(...)  (x5)
  -> \\\\\\\[3] set\\\\\\\_daily\\\\\\\_hours({"hours": 3})
  -> \\\\\\\[4] generate\\\\\\\_schedule({"days": 30})
agent> Added 5 tasks. Heavy week ahead: Machine Design revision is at risk by 2.5h...

you> I'm travelling on 2026-11-08, replan.
  -> block\\\\\\\_date(...) -> generate\\\\\\\_schedule(...)
```

## Tests

```bash
python -m pytest -q          # 12 tests: planner, tools, storage, sandbox
python export\\\\\\\_schema.py      # regenerate docs/tools\\\\\\\_schema.json from the code
```

## Project structure

```
agent.py            LLM agent loop + CLI
tools.py            Toolkit: the 10 tools (docstrings = tool schema)
planner.py          Deterministic scheduling algorithm
storage.py          Atomic JSON persistence
export\\\\\\\_schema.py    Generates docs/tools\\\\\\\_schema.json
docs/               Architecture diagram + tool schema
data/inputs/        Sample syllabus for the agent to read
tests/              Unit tests
```

## Configuration

|Variable|Default|Meaning|
|-|-|-|
|`GEMINI\\\\\\\_API\\\\\\\_KEY`|none (required)|Google AI Studio key|
|`GEMINI\\\\\\\_MODEL`|`gemini-3.1-flash-lite`|Change if the model is retired or rate-limited|
|`PLANNER\\\\\\\_DATA`|`data/state.json`|Where state is stored|

## Limitations and future work

* Single user, JSON storage (swap `storage.py` for SQLite to scale).
* No calendar sync; a Google Calendar tool would be a natural extension.
* Estimates come from the user; the agent could learn actual vs estimated hours from `log\\\\\\\_progress`.

