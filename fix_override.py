with open("api/main.py") as f:
    text = f.read()

text = text.replace('if draft:\n        final_msg = "OVERRIDE TEST: " + draft\n', "if draft:\n")

with open("api/main.py", "w") as f:
    f.write(text)
