with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    "IMPORTANT: Do not invent any numbers or facts. ONLY use the numbers explicitly provided \\\nin the System Information. NEVER repeat the numbers from the Customer Message unless they \\\nare also in the System Information. Rewrite the system information to be more empathetic.",
    'RULES:\n1. Rephrase the system information into a natural, friendly reply.\n2. Do NOT mention the phrase "System Information".\n3. ONLY use the numbers provided in the system information.\n4. NEVER repeat unverified numbers from the customer.',
)

with open("api/main.py", "w") as f:
    f.write(text)
