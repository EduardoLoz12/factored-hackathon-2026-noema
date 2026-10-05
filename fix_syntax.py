with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    'parsed = json.loads(draft.strip("` \n\n").removeprefix("json"))',
    'parsed = json.loads(draft.strip("` \\n").removeprefix("json"))',
)
# Also fix any other ones
import re

text = re.sub(r'draft\.strip\("` \n.*?"\)', 'draft.strip("` \\\\n")', text, flags=re.DOTALL)

with open("api/main.py", "w") as f:
    f.write(text)
