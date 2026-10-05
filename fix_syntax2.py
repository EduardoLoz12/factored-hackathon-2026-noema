with open("api/main.py") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "parsed = json.loads(draft.strip" in line:
        lines[i] = '            parsed = json.loads(draft.strip("` \\n").removeprefix("json"))\n'
    if '").removeprefix("json"))' in line and i > 700 and i < 730:
        lines[i] = ""  # Remove the leftover

with open("api/main.py", "w") as f:
    f.writelines(lines)
