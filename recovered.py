Created At: 2026-10-02T23:50:34-06:00
Completed At: 2026-10-02T23:50:35-06:00

The command exited with code 0.
Output:
import os
import time

import duckdb
import joblib
import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Noema AI-First Banking Core", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SemanticCognitionMatrix:
    def evaluate(self, text: str) -> dict:
        text = text.lower()
        if "angry" in text or "human" in text or "escalate" in text or "frustrated" in text:
            return {"intent": "escalation"}
        else:
            return {"intent": "banking_inquiry"}


def get_customer_data(customer_id: str) -> dict:
    try:
        con = duckdb.connect("data/noema.duckdb", read_only=True)
        df = con.execute(
            f"SELECT first_name, segment, total_balance_usd, estimated_monthly_income, days_past_due FROM noema_gold.customer_360 WHERE customer_id = '{customer_id}'"
        ).df()
        con.close()
        if not df.empty:
            return df.to_dict("records")[0]
    except Exception as e:
        print(f"DB Error: {e}")
    return {}


class NoemaCore:
    def __init__(self):
        self.scm = SemanticCognitionMatrix()
        self.api_key = os.getenv("GEMINI_API_KEY")

    def process(self, query: str, history: str, customer_id: str) -> dict:
        scm_result = self.scm.evaluate(query)
        intent = scm_result["intent"]

        if intent == "escalation":
            return {
                "action": "escalate",
                "msg": "I understand your frustration. I am transferring you to a human expert right now.",
            }

        if not self.api_key or len(self.api_key) < 10 or self.api_key == "your_copied_api_key_here":
            return {
                "action": "respond",
                "msg": "I am Noema! Please set a valid GEMINI_API_KEY in your .env file.",
            }

        # Fetch REAL data from DuckDB to ground the LLM
        cust_data = get_customer_data(customer_id)
        cust_context = ""
        if cust_data:
            cust_context = f"""
Customer Profile (REAL DATA):
- Name: {cust_data.get('first_name', 'Customer')}
- Segment: {cust_data.get('segment', 'Standard')}
- Total Balance: ${cust_data.get('total_balance_usd', 0):,.2f} USD
- Monthly Income: ${cust_data.get('estimated_monthly_income', 0):,.2f}
- Days Past Due: {cust_data.get('days_past_due', 0)}
"""

        for attempt in range(2):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={self.api_key}"
                prompt = f"""
You are Noema, an AI Banking Agent for Factored Bank.
DO NOT introduce yourself. Answer the user's latest query directly and conversationally.
You must ground your answers in the customer's REAL profile data below. Never invent balances or fake credit card names (recommend 'Factored Premium Card' or 'Factored Standard Card' instead).

{cust_context}

Chat history:
{history}
"""
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, json=payload, timeout=20)
                data = res.json()

                if "error" in data:
                    if attempt == 0 and "demand" in data["error"].get("message", "").lower():
                        time.sleep(2)
                        continue
                    return {
                        "action": "respond",
                        "msg": f"Gemini API Error: {data['error'].get('message', str(data))}",
                    }

                text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                return {"action": "respond", "msg": text_response}

            except Exception as e:
                return {"action": "respond", "msg": f"An error occurred calling the LLM: {str(e)}"}

        return {
            "action": "respond",
            "msg": "I am currently experiencing high network demand. Please try asking again in a few moments.",
        }


noema_core = NoemaCore()

try:
    escalation_model_data = joblib.load("data/models/support_escalation.joblib")
    escalation_model = escalation_model_data["model"]
except Exception:
    escalation_model = None


class ChatRequest(BaseModel):
    customer_id: str
    message: str
    history: str = ""
    channel: str = "chatbot"
    interaction_type: str = "inbound"
    reason_category: str = "general_inquiry"


class ChatResponse(BaseModel):
    response: str
    escalate_to_human: bool
    action_taken: str | None = None


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    core_result = noema_core.process(request.message, request.history, request.customer_id)

    escalate = False
    if escalation_model and core_result["action"] != "escalate":
        df = pd.DataFrame(
            [
                {
                    "channel": request.channel,
                    "interaction_type": request.interaction_type,
                    "reason_category": request.reason_category,
                }
            ]
        )
        prob = escalation_model.predict_proba(df)[0][1]
        if prob > 0.5:
            escalate = True

    if core_result["action"] == "escalate" or escalate:
        return ChatResponse(
            response="I am transferring you to a human expert who can better assist you right away.",
            escalate_to_human=True,
            action_taken="escalation",
        )

    return ChatResponse(
        response=core_result["msg"], escalate_to_human=False, action_taken=core_result["action"]
    )


@app.get("/health")
def health():
    return {"status": "ok"}
