with open("api/main.py") as f:
    text = f.read()

text = text.replace("                if draft:", "        if draft:")

with open("api/main.py", "w") as f:
    f.write(text)
