import os

import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
final_msg = "Demo identity verified for Sandra Suárez Moreno. You can now ask for account facts available in this local demo."
request_message = "Hi my name is Sandra Suárez Moreno"
prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
System Information: "{final_msg}"
Customer Message: "{request_message}"
IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
"""
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
payload = {"contents": [{"parts": [{"text": prompt}]}]}
res = requests.post(url, json=payload, timeout=10)
print(res.json()["candidates"][0]["content"]["parts"][0]["text"])
