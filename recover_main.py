import re

out_lines = {}
current_block = None

with open("recovered_chunk2.py") as f:
    for line in f:
        if "Showing lines 1 to 800" in line:
            current_block = "1-800"
            continue
        elif "Showing lines 801 to 1350" in line:
            current_block = "801-1350"
            continue
        elif "Showing lines" in line:
            current_block = None
            continue

        if current_block and re.match(r"^(\d+): (.*)", line):
            m = re.match(r"^(\d+): (.*)", line)
            line_num = int(m.group(1))
            content = m.group(2)
            out_lines[line_num] = content
        elif current_block and re.match(r"^(\d+):\s*$", line):
            m = re.match(r"^(\d+):\s*$", line)
            line_num = int(m.group(1))
            out_lines[line_num] = ""

with open("api/main.py", "w") as f:
    for i in range(1, 1351):
        f.write(out_lines.get(i, "") + "\n")

print("Recovered lines:", len(out_lines))
