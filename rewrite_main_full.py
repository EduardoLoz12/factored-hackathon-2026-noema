with open("api/main.py") as f:
    text = f.read()

# ADD _generate_with_llm
generate_func = """
def _generate_with_llm(prompt: str) -> str:
    import os, requests
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or len(api_key) < 10 or api_key == "your_copied_api_key_here":
        return ""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("llm_generation_failed type=%s", type(e).__name__)
        return ""

def _slots_from_message(text: str, intent: str) -> dict:"""

text = text.replace("def _slots_from_message(text: str, intent: str) -> dict:", generate_func)

# ADD Slot extraction LLM
slot_orig = """def _slots_from_message(text: str, intent: str) -> dict:
    slots: dict[str, object] = {}
    product_type = _product_type_from_text(text)"""

slot_new = '''def _slots_from_message(text: str, intent: str) -> dict:
    import json
    prompt = f"""Extract banking slots from this message for intent: {intent}.
Message: "{text}"
Respond ONLY with a valid JSON object matching this exact schema:
{{"product_type": "credit_card"|"loan"|null, "requested_amount": float|null, "currency": "USD"|"EUR"|null}}"""
    draft = _generate_with_llm(prompt)
    if draft:
        try:
            parsed = json.loads(draft.strip("` \n").removeprefix("json"))
            return parsed
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("llm_slot_extraction_failed type=%s", type(e).__name__)

    # Fallback
    slots: dict[str, object] = {}
    product_type = _product_type_from_text(text)'''

text = text.replace(slot_orig, slot_new)

with open("api/main.py", "w") as f:
    f.write(text)
