import re

with open("api/main.py") as f:
    text = f.read()

# remove my broken sed:
# with open("draft.log", "a") as f: f.write(f"PROMPT:\n{prompt}\n\nDRAFT:\n{draft}\n====\n")
#     if draft:

text = re.sub(
    r'with open\("draft\.log", "a"\) as f: f\.write\(f"PROMPT:\\n\{prompt\}\\n\\nDRAFT:\\n\{draft\}\\n====\\n"\)\n    if draft:',
    "        if draft:",
    text,
)

# fix the LLM error
text = text.replace('return f"LLM ERROR: {repr(e)}"', 'return ""')
text = text.replace(
    'print("LLM ERROR:", repr(e))',
    'LOGGER.warning("llm_generation_failed type=%s", type(e).__name__)',
)

with open("api/main.py", "w") as f:
    f.write(text)
