import re

with open("api/main.py") as f:
    text = f.read()

new_prompt = """        feedback = f"\\n\\nWARNING - PREVIOUS ATTEMPT FAILED: {_previous.motivo}. You MUST strictly fix this by ONLY using numbers from the System Information." if _previous else ""
        prompt = f\"\"\"You are a helpful and polite human-like banking assistant.
Rephrase the system information below into a natural, empathetic reply to the customer.

RULES:
1. You must use the EXACT numbers from the System Information.
2. DO NOT invent any numbers.
3. Keep the response entirely in a single language (English or Spanish based on the customer message).
4. DO NOT mention the phrase 'System Information'.

System Information: "{context}"
Customer Message: "{request.message}"{feedback}
\"\"\""""

# We need to replace the old prompt. Let's just find the exact block and replace it.
text = re.sub(r'        feedback = f"\\n\\nWARNING.*?"""', new_prompt, text, flags=re.DOTALL)

with open("api/main.py", "w") as f:
    f.write(text)
