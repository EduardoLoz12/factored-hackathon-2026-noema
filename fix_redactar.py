import re

with open("api/main.py") as f:
    text = f.read()

# Replace exactly lines 824 to 828.
text = re.sub(
    r'        feedback = \(\n.*?\n        \) if _previous else ""',
    '        feedback = (\n            f"\\n\\nWARNING: {_previous.motivo}. "\n            "ONLY use numbers from System Information."\n        ) if _previous else ""',
    text,
    flags=re.DOTALL,
)

with open("api/main.py", "w") as f:
    f.write(text)
