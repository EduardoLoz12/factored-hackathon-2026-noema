with open("api/main.py") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if line.startswith("            if draft:") and lines[i + 1].startswith(
        "        final_msg = draft"
    ):
        if lines[i - 1].startswith("    draft ="):
            new_lines.append("    if draft:\n")
        elif lines[i - 1].startswith("        draft ="):
            new_lines.append("        if draft:\n")
        elif lines[i - 1].startswith("            draft ="):
            new_lines.append("            if draft:\n")
        else:
            new_lines.append(line)
    else:
        new_lines.append(line)

with open("api/main.py", "w") as f:
    f.writelines(new_lines)
