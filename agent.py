"""Study Planner Agent: a Gemini-powered tool-using agent.

The loop is written out explicitly (no automatic function calling) so the
Think -> Act -> Observe cycle is visible:

    user goal -> LLM decides -> calls tools -> sees results -> repeats -> final answer
"""
import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from tools import Toolkit

load_dotenv()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MAX_STEPS = 12  # safety cap on tool-call rounds per user message

SYSTEM_PROMPT = """You are Study Planner, an autonomous agent that helps a college student organise their studies.

How you work:
- You can ONLY change the planner by calling tools. Never claim you added, changed or scheduled something unless a tool result confirms it.
- If the user uses relative dates ("tomorrow", "next Friday"), call get_current_date first and convert to YYYY-MM-DD.
- If the user gives a syllabus or deadline file name, call read_text_file, extract every task, then add each with add_task.
- After adding, deleting or changing tasks, daily hours or blocked dates, call generate_schedule so the plan stays current.
- Check at_risk in the schedule result. If tasks are at risk, say which ones, by how many hours, and suggest concrete fixes (raise daily hours, drop a blocked date, move a deadline, lower scope).
- If essential information is missing (a deadline or an effort estimate), ask ONE short question instead of guessing. For a missing priority, use 2.
- Never invent task ids. Use list_tasks to look them up.
- Keep final answers short and practical: use a day-by-day list for plans, plain sentences otherwise."""


def make_config(toolkit):
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=toolkit.tools,
        # We run the tool loop ourselves so every step is visible.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )


def _generate(client, contents, config, retries=6):
    """Call the model, retrying on rate-limit / overload errors."""
    for attempt in range(retries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config)
        except genai_errors.APIError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  [model busy ({e.code}); retrying in {wait}s]")
                time.sleep(wait)
                continue
            raise


def run_turn(client, toolkit, contents, config, verbose=False):
    """Process one user message. `contents` is the running conversation and is
    updated in place. Returns the agent's final text answer."""
    for step in range(1, MAX_STEPS + 1):
        response = _generate(client, contents, config)
        if not response.candidates or response.candidates[0].content is None:
            return "(The model returned no answer. Please rephrase your request.)"
        message = response.candidates[0].content
        contents.append(message)

        calls = [p.function_call for p in (message.parts or []) if p.function_call]
        if not calls:  # no more tools needed -> final answer
            return "".join(p.text for p in message.parts if p.text).strip()

        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            print(f"  -> [{step}] {call.name}({json.dumps(args, ensure_ascii=False)})")
            result = toolkit.call(call.name, args)
            shown = json.dumps(result, ensure_ascii=False)
            print(f"  <- {shown if verbose or len(shown) < 160 else shown[:157] + '...'}")
            result_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=result_parts))

    return "I hit my step limit before finishing. Please try a smaller request."


def main():
    parser = argparse.ArgumentParser(description="Study Planner Agent (Gemini)")
    parser.add_argument("--verbose", action="store_true", help="print full tool results")
    parser.add_argument("--reset", action="store_true", help="clear saved planner data first")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Set GEMINI_API_KEY (copy .env.example to .env). "
                 "Free key: https://aistudio.google.com/apikey")

    toolkit = Toolkit()
    if args.reset and toolkit.store.path.exists():
        toolkit.store.path.unlink()
        print("Planner data cleared.")

    client = genai.Client(api_key=api_key)
    config = make_config(toolkit)
    contents = []  # conversation memory for this session

    print(f"Study Planner Agent ({MODEL}). Type 'quit' to exit.")
    print("Try: 'I have a thermodynamics exam on 2026-11-20 needing 12 hours of prep. Plan my week.'\n")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user.lower() in {"quit", "exit"}:
            break
        if not user:
            continue
        contents.append(types.Content(role="user", parts=[types.Part(text=user)]))
        try:
            answer = run_turn(client, toolkit, contents, config, args.verbose)
        except genai_errors.APIError as e:
            answer = f"(Model error {e.code}: {e.message})"
        print(f"\nagent> {answer}\n")


if __name__ == "__main__":
    main()