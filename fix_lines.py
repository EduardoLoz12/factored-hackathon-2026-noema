with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    '{{"product_type": "credit_card"|"loan"|null, "requested_amount": float|null, "currency": "USD"|"EUR"|null}}"""',
    '{{"product_type": "credit_card"|"loan"|null,\n "requested_amount": float|null, "currency": "USD"|"EUR"|null}}"""',
)

text = text.replace(
    'logging.getLogger(__name__).warning("llm_slot_extraction_failed type=%s", type(e).__name__)',
    'logging.getLogger(__name__).warning(\n                "llm_slot_extraction_failed type=%s", type(e).__name__\n            )',
)

text = text.replace(
    "You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:",
    "You are a helpful banking assistant. Draft a natural, conversational response \\\nto the customer based on this verified system information:",
)

text = text.replace(
    "IMPORTANT: Do not invent any numbers. Only use the numbers and facts provided in the System Information.",
    "IMPORTANT: Do not invent any numbers. Only use the numbers \\\nand facts provided in the System Information.",
)

text = text.replace(
    "IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information. Rewrite the system information to be more empathetic and human-like.",
    "IMPORTANT: Do not invent any numbers or facts. Only use the facts provided \\\nin the System Information. Rewrite the system information to be more empathetic.",
)

with open("api/main.py", "w") as f:
    f.write(text)
