with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    'return data["candidates"][0]["content"]["parts"][0]["text"]',
    'ret = data["candidates"][0]["content"]["parts"][0]["text"]\n        with open("llm_success.log", "w") as f: f.write(ret)\n        return ret',
)

with open("api/main.py", "w") as f:
    f.write(text)
