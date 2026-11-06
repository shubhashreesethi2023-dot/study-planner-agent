"""Print the Gemini models your API key can use for chat / tool calling.

Usage: python list_models.py
Then put one of the printed names in .env as GEMINI_MODEL=<name>
"""
import os
import sys

from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.environ.get("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY is missing. Check your .env file.")

client = genai.Client(api_key=key)
names = []
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or []
    if "generateContent" in actions:
        names.append(m.name.replace("models/", ""))

print("Models you can use (copy one into .env as GEMINI_MODEL=...):\n")
for name in sorted(names):
    print("  " + name)
