with open("api/main.py") as f:
    text = f.read()

# Replace the redactar prompt
old_prompt = """        prompt = f\"\"\"RULES:
1. Rephrase the system information into a natural, friendly reply.
2. Do NOT mention the phrase "System Information".
3. ONLY use the facts provided in the system information.

System Information: "{context}"
Customer Message: "{request.message}"
IMPORTANT: Do not invent any numbers or facts. ONLY use the numbers explicitly provided \\
in the System Information. NEVER repeat the numbers from the Customer Message unless they \\
are also in the System Information. Rewrite the system information to be more empathetic.
\"\"\""""

new_prompt = """        feedback = f"\\n\\nWARNING - PREVIOUS ATTEMPT FAILED: {_previous.motivo}. You MUST strictly fix this by ONLY using numbers from the System Information." if _previous else ""
        prompt = f\"\"\"You are a helpful and polite human-like banking assistant.
Rephrase the system information below into a natural, empathetic reply to the customer.

RULES:
1. You must use the EXACT numbers from the System Information.
2. DO NOT invent any numbers.
3. DO NOT mention the phrase 'System Information'.

System Information: "{context}"{feedback}
\"\"\""""

text = text.replace(old_prompt, new_prompt)

with open("api/main.py", "w") as f:
    f.write(text)
