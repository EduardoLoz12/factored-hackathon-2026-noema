with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    "IMPORTANT: Do not invent any numbers or facts. Only use the facts provided \\\nin the System Information. Rewrite the system information to be more empathetic.",
    "IMPORTANT: Do not invent any numbers or facts. ONLY use the numbers explicitly provided \\\nin the System Information. NEVER repeat the numbers from the Customer Message unless they are also in the System Information. Rewrite the system information to be more empathetic.",
)

with open("api/main.py", "w") as f:
    f.write(text)
