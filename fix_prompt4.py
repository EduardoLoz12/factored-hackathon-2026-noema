with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    "IMPORTANT: Do not invent any numbers or facts. Only use the facts provided \\\nin the System Information. Rewrite the system information to be more empathetic.",
    'RULES:\n1. Rephrase the system information into a natural, friendly reply.\n2. Do NOT mention the phrase "System Information".\n3. ONLY use the facts provided in the system information.',
)

with open("api/main.py", "w") as f:
    f.write(text)
