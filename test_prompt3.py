import os

import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
final_msg = "I can use Sandra's verified demo profile. I can show balance, estimated income, segment, active products, and product catalog details. I can also run our eligibility policy check for credit options when you give a product, amount, and currency."
request_message = "What can you do for me?"
prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
System Information: "{final_msg}"
Customer Message: "{request_message}"
IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information. Rewrite the system information to be more empathetic and conversational.
"""
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
payload = {"contents": [{"parts": [{"text": prompt}]}]}
res = requests.post(url, json=payload, timeout=10)
print(res.json()["candidates"][0]["content"]["parts"][0]["text"])
