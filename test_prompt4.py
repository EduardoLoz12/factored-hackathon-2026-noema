from dotenv import load_dotenv

load_dotenv()
import os

import requests

api_key = os.getenv("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
prompt = "Hello"
payload = {"contents": [{"parts": [{"text": prompt}]}]}
res = requests.post(url, json=payload, timeout=10)
print(res.json())
