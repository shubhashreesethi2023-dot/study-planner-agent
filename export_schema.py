"""Export the tool schema (what the LLM sees) to docs/tools_schema.json.

The schema is generated from tools.py itself (type hints + docstrings), in the
same function-declaration format Gemini uses, so docs can never drift from code.

Usage: python export_schema.py
"""
import inspect
import json
import re
from pathlib import Path

from tools import Toolkit

TYPE_MAP = {str: "STRING", int: "INTEGER", float: "NUMBER", bool: "BOOLEAN"}


def parse_docstring(doc):
    """Split a docstring into (description, {param: description})."""
    doc = inspect.cleandoc(doc or "")
    main, _, args_block = doc.partition("Args:")
    params = {}
    for line in args_block.splitlines():
        m = re.match(r"\s*(\w+):\s*(.+)", line)
        if m:
            params[m.group(1)] = m.group(2).strip()
    return " ".join(main.split()), params


def declaration(fn):
    description, param_docs = parse_docstring(fn.__doc__)
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {
            "type": TYPE_MAP[p.annotation],
            "description": param_docs.get(name, ""),
        }
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "name": fn.__name__,
        "description": description,
        "parameters": {"type": "OBJECT", "properties": props, "required": required},
    }


if __name__ == "__main__":
    decls = [declaration(fn) for fn in Toolkit().tools]
    out = Path("docs/tools_schema.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"tools": decls}, indent=2), encoding="utf-8")
    print(f"Wrote {len(decls)} tool schemas to {out}")
