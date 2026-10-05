with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    'LOGGER.error("llm_generation_failed: %s", repr(e))',
    'with open("llm_error.log", "w") as f: f.write(repr(e))',
)

with open("api/main.py", "w") as f:
    f.write(text)
