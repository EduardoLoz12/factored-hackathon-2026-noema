import json
import logging
import os
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import joblib
import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.core.orchestrator import Desenlace, Orquestador, Turno
from agent.policies.engine import Cliente, Politica, ProductoVigente
from agent.tools import cases as case_tools
from agent.tools import credit as credit_tools
from agent.tools import customer as customer_tools
from agent.tools.ledger import abrir_ledger
from agent.tools.registry import Role, Session, ToolRegistry
from agent.tools.store import Contexto, abrir_analitica

load_dotenv()

LOGGER = logging.getLogger(__name__)
TRACE_DIR = Path("logs/traces")
TRACE_FILE = TRACE_DIR / "chat_interactions.jsonl"
ANALYTICS_DB = Path(os.getenv("NOEMA_ANALYTICS_DB", "data/noema.duckdb"))
LEDGER_DB = os.getenv("NOEMA_LEDGER_DB", "data/noema_ledger.duckdb")
ORCHESTRATOR_CUTOFF = date(2025, 12, 31)

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
        if any(
            term in text
            for term in (
                "angry",
                "asesor",
                "atendente",
                "frustrated",
                "human",
                "humano",
                "persona",
                "escalate",
            )
        ):
            return {"intent": "escalation"}
        if any(term in text for term in ("balance", "saldo", "balances")):
            return {"intent": "balance"}
        if any(
            term in text
            for term in (
                "monthly income",
                "montly income",
                "income",
                "ingreso mensual",
                "ingreso",
            )
        ):
            return {"intent": "income"}
        if any(
            term in text
            for term in (
                "what can you do",
                "help me with",
                "capabilities",
                "que puedes hacer",
                "qué puedes hacer",
            )
        ):
            return {"intent": "capabilities"}
        if any(
            term in text for term in ("recommend", "recommendation", "recomienda", "recomendar")
        ):
            return {"intent": "recommendation"}
        if re.search(
            r"\b(best|mejor|which|cu[aá]l|suitable|conviene|for me|para m[ií])\b",
            text,
        ) and any(term in text for term in ("card", "tarjeta", "credit", "crédito", "credito")):
            return {"intent": "recommendation"}
        if any(
            term in text
            for term in (
                "obligation",
                "obligacion",
                "obligación",
                "capacity",
                "capacidad",
                "terms",
                "options",
                "opciones",
            )
        ):
            return {"intent": "financial_profile"}
        if any(term in text for term in ("eligible", "eligib", "loan", "credito", "crédito")):
            return {"intent": "eligibility"}
        if any(term in text for term in ("product", "producto", "card", "tarjeta")):
            return {"intent": "products"}
        if re.search(r"\b(i am|i'm|my name is|soy|me llamo)\b", text):
            return {"intent": "identity_claim"}
        return {"intent": "unknown"}


def _normalizar_nombre(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _extract_claimed_name(text: str) -> str | None:
    match = re.search(
        r"\b(?:i am|i'm|my name is|soy|me llamo)\s+(.+)$",
        text.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    claimed = re.split(r"[,.!?;:]", match.group(1), maxsplit=1)[0]
    return claimed.strip() or None


def get_customer_data(customer_id: str) -> dict:
    try:
        with duckdb.connect("data/noema.duckdb", read_only=True) as con:
            df = con.execute(
                """
                SELECT first_name, last_name, country, segment, total_balance_usd,
                       estimated_monthly_income, days_past_due
                FROM noema_gold.customer_360
                WHERE customer_id = ?
                """,
                [customer_id],
            ).df()
        if not df.empty:
            return df.to_dict("records")[0]
    except Exception as e:
        LOGGER.warning("customer_lookup_failed type=%s", type(e).__name__)
    return {}


def find_customer_by_name(full_name: str | None) -> dict:
    if not full_name:
        return {}
    normalized_claim = _normalizar_nombre(full_name)
    try:
        with duckdb.connect("data/noema.duckdb", read_only=True) as con:
            df = con.execute(
                """
                SELECT customer_id, first_name, last_name, country, segment, total_balance_usd,
                       estimated_monthly_income, days_past_due
                FROM noema_gold.customer_360
                """,
            ).df()
        if df.empty:
            return {}
        df["full_name"] = (
            df["first_name"].fillna("").astype(str).str.strip()
            + " "
            + df["last_name"].fillna("").astype(str).str.strip()
        )
        matches = df[df["full_name"].map(_normalizar_nombre) == normalized_claim]
        if not matches.empty:
            return matches.iloc[0].to_dict()
    except Exception as e:
        LOGGER.warning("customer_name_lookup_failed type=%s", type(e).__name__)
    return {}


def get_customer_products(customer_id: str) -> list[dict]:
    if not customer_id:
        return []
    try:
        with duckdb.connect("data/noema.duckdb", read_only=True) as con:
            df = con.execute(
                """
                SELECT product_id, product_type, currency, current_balance, credit_limit,
                       interest_rate, product_status, days_past_due
                FROM noema_silver.stg_products
                WHERE customer_id = ?
                  AND product_status = 'Active'
                ORDER BY product_type, product_id
                """,
                [customer_id],
            ).df()
        return df.to_dict("records")
    except Exception as e:
        LOGGER.warning("customer_products_lookup_failed type=%s", type(e).__name__)
    return []


def _product_catalog_names() -> str:
    return ", ".join(item["producto"] for item in Politica.cargar().catalogo)


def _credit_card_terms() -> dict:
    for item in Politica.cargar().catalogo:
        if item["producto"] == "Tarjeta Crédito":
            return item
    return {}


def _financial_profile_message(
    customer: dict,
    products: list[dict],
    identity_verified_demo: bool,
) -> str:
    if not identity_verified_demo:
        return (
            "I need to verify the demo identity before showing income, obligations, "
            "capacity, or card options. Type: my name is <your full name>."
        )
    if not customer:
        return (
            "I cannot find a verified customer profile for this demo session, so I will not "
            "invent income, obligations, capacity, or card options."
        )

    first_name = customer.get("first_name", "there")
    segment = customer.get("segment") or "unknown"
    income = customer.get("estimated_monthly_income")
    balance = float(customer.get("total_balance_usd") or 0)
    credit_product_types = {
        "Tarjeta Crédito",
        "Préstamo Personal",
        "Préstamo Hipotecario",
    }
    active_credit = [
        product for product in products if product.get("product_type") in credit_product_types
    ]
    active_deposit = [
        product for product in products if product.get("product_type") not in credit_product_types
    ]
    card = _credit_card_terms()
    income_text = (
        f"${float(income):,.2f} monthly estimated income"
        if income is not None
        else "no estimated monthly income value in the loaded profile"
    )
    credit_obligation_text = (
        f"{len(active_credit)} active credit obligation(s)"
        if active_credit
        else "no active credit obligations found in the active product records"
    )
    capacity_text = (
        "capacity is not fully computed in the main chatbot yet; the deterministic "
        "eligibility engine still needs verified credit-product details and policy evaluation"
    )
    card_terms = (
        f"Tarjeta Crédito is available to segments {', '.join(card.get('segmentos', []))}; "
        f"catalog range ${float(card.get('monto_minimo_usd', 0)):,.0f}-"
        f"${float(card.get('monto_maximo_usd', 0)):,.0f} USD; "
        f"annual rate {float(card.get('tasa_anual', 0)):.2f}%; "
        f"amortization={card.get('amortizacion', 'unknown')}."
        if card
        else "Tarjeta Crédito terms were not found in the policy catalog."
    )
    segment_fit = (
        "Your Plus segment is within the catalog segment list for Tarjeta Crédito."
        if segment in set(card.get("segmentos", []))
        else "Your segment is not in the catalog segment list for Tarjeta Crédito."
    )
    return (
        f"{first_name}, here are the verified inputs I can show: income={income_text}; "
        f"segment={segment}; recorded total balance=${balance:,.2f} USD; "
        f"active deposit/account products={len(active_deposit)}; "
        f"obligations={credit_obligation_text}; "
        f"capacity={capacity_text}. For credit-card options: {card_terms} {segment_fit} "
        "This is not an approval or final recommendation; it is the grounded input summary "
        "needed before the policy engine can make an eligibility decision."
    )


def _income_message(customer: dict, identity_verified_demo: bool) -> str:
    if not identity_verified_demo:
        return (
            "I need to verify the demo identity before showing income. "
            "Type: my name is <your full name>."
        )
    if not customer:
        return "I cannot find a verified customer profile, so I will not invent income."
    income = customer.get("estimated_monthly_income")
    first_name = customer.get("first_name", "this customer")
    country = customer.get("country") or "the source profile"
    if income is None:
        return f"I do not have an estimated monthly income value for {first_name}."
    return (
        f"{first_name}'s estimated monthly income is {float(income):,.2f} "
        f"in the source customer profile for {country}. This field is not the USD "
        "balance; it is the stored income estimate from the customer record."
    )


def _capabilities_message(identity_verified_demo: bool) -> str:
    identity_note = (
        "I can use Sandra's verified demo profile."
        if identity_verified_demo
        else "First verify the demo identity by typing: my name is <your full name>."
    )
    return (
        f"{identity_note} I can show balance, estimated income, segment, active products, "
        "and product catalog details. I can also run our eligibility policy check "
        "for credit options when you give a product, amount, and currency."
    )


def _recommendation_message(customer: dict, identity_verified_demo: bool) -> str:
    if not identity_verified_demo:
        return (
            "I need to verify the demo identity before making account-specific suggestions. "
            "Type: my name is <your full name>."
        )
    if not customer:
        return (
            "I cannot find a verified customer profile for this demo session, so I will not "
            "invent a recommendation."
        )
    first_name = customer.get("first_name", "there")
    balance = float(customer.get("total_balance_usd") or 0)
    segment = customer.get("segment") or "unknown"
    days_past_due = customer.get("days_past_due")
    catalog = _product_catalog_names()
    delinquency_note = (
        f"The profile shows {days_past_due:.0f} days past due, so the safest next step is to "
        "resolve the overdue status before exploring new credit."
        if days_past_due is not None and float(days_past_due) > 0
        else "I do not see an overdue-days flag in the loaded profile, so the safe next step is "
        "to review available products without treating them as approved offers."
    )
    return (
        f"{first_name}, based on the verified local profile I can see segment={segment} and "
        f"recorded balance=${balance:,.2f} USD. {delinquency_note} The current policy catalog "
        f"contains: {catalog}. My practical recommendation is to ask for the product catalog "
        "or a policy eligibility check next; I will not claim you are approved until the "
        "deterministic eligibility engine evaluates the required facts."
    )


class NoemaCore:
    def __init__(self):
        self.scm = SemanticCognitionMatrix()
        self.api_key = os.getenv("GEMINI_API_KEY")

    def process(
        self,
        query: str,
        history: str,
        customer_id: str,
        identity_verified_demo: bool = False,
    ) -> dict:
        scm_result = self.scm.evaluate(query)
        intent = scm_result["intent"]

        if intent == "escalation":
            return {
                "action": "escalate",
                "provider_attempted": False,
                "msg": (
                    "I understand your frustration. I am transferring you to a human "
                    "expert right now."
                ),
            }

        cust_data = get_customer_data(customer_id)
        products = get_customer_products(customer_id)
        if intent == "balance":
            if not identity_verified_demo:
                return {
                    "action": "abstain",
                    "provider_attempted": False,
                    "identity_verified_demo": False,
                    "msg": (
                        "I need to verify the demo identity before showing account "
                        "balances. Type: my name is <your full name>."
                    ),
                }
            if not cust_data:
                return {
                    "action": "abstain",
                    "provider_attempted": False,
                    "identity_verified_demo": identity_verified_demo,
                    "msg": (
                        "I cannot find a verified customer profile for this demo customer ID, "
                        "so I will not invent a balance."
                    ),
                }
            return {
                "action": "respond",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": (
                    f"For {cust_data.get('first_name', 'this customer')}, the recorded total "
                    f"balance is ${cust_data.get('total_balance_usd', 0):,.2f} USD. "
                    "This comes from the local DuckDB customer_360 table."
                ),
            }

        if intent == "income":
            return {
                "action": "respond",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": _income_message(cust_data, identity_verified_demo),
            }

        if intent == "identity_claim":
            claimed_name = _extract_claimed_name(query)
            matched_customer = find_customer_by_name(claimed_name)
            stored_name = _display_name(matched_customer)
            if not matched_customer:
                return {
                    "action": "abstain",
                    "provider_attempted": False,
                    "claimed_name": claimed_name,
                    "identity_match": False,
                    "identity_verified_demo": False,
                    "msg": (
                        f"I cannot verify the name '{claimed_name}'. Please check the full "
                        "name and try again."
                    ),
                }
            if claimed_name and _normalizar_nombre(claimed_name) == _normalizar_nombre(stored_name):
                return {
                    "action": "verify_identity",
                    "provider_attempted": False,
                    "claimed_name": claimed_name,
                    "identity_match": True,
                    "identity_verified_demo": True,
                    "verified_customer_id": matched_customer.get("customer_id"),
                    "verified_display_name": stored_name,
                    "verified_segment": matched_customer.get("segment"),
                    "msg": (
                        f"Demo identity verified for {stored_name}. You can now ask for "
                        "account facts available in this local demo."
                    ),
                }
            return {
                "action": "abstain",
                "provider_attempted": False,
                "claimed_name": claimed_name,
                "identity_match": False,
                "identity_verified_demo": False,
                "msg": (
                    f"I cannot verify the name '{claimed_name}'. Please check the full "
                    "name and try again."
                ),
            }

        if intent == "eligibility":
            return {
                "action": "abstain",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": (
                    _financial_profile_message(cust_data, products, identity_verified_demo)
                    + " Ask me to run a policy eligibility check once that route is connected "
                    "to the live UI action."
                ),
            }

        if intent == "financial_profile":
            return {
                "action": "respond",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": _financial_profile_message(cust_data, products, identity_verified_demo),
            }

        if intent == "capabilities":
            return {
                "action": "respond",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": _capabilities_message(identity_verified_demo),
            }

        if intent == "recommendation":
            return {
                "action": "respond",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": _recommendation_message(cust_data, identity_verified_demo),
            }

        if intent == "products":
            catalog = _product_catalog_names()
            return {
                "action": "respond",
                "provider_attempted": False,
                "identity_verified_demo": identity_verified_demo,
                "msg": (
                    "The versioned policy catalog contains these products: "
                    f"{catalog}. These are not offers until the policy engine evaluates "
                    "verified customer facts."
                ),
            }

        return {
            "action": "abstain",
            "provider_attempted": False,
            "identity_verified_demo": identity_verified_demo,
            "msg": (
                "I do not have a grounded tool-backed answer for that request yet. "
                "I will not guess or invent banking information."
            ),
        }

    def generate_with_llm(self, query: str, history: str, customer_id: str) -> dict:
        if not self.api_key or len(self.api_key) < 10 or self.api_key == "your_copied_api_key_here":
            return {
                "action": "abstain",
                "provider_attempted": False,
                "msg": "No valid language-model provider is configured.",
            }
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={self.api_key}"
            payload = {"contents": [{"parts": [{"text": query + "\n" + history}]}]}
            res = requests.post(url, json=payload, timeout=20)
            data = res.json()
            text_response = data["candidates"][0]["content"]["parts"][0]["text"]
            return {"action": "respond", "provider_attempted": True, "msg": text_response}
        except Exception as e:
            LOGGER.warning("llm_call_failed type=%s", type(e).__name__)
            return {
                "action": "abstain",
                "provider_attempted": True,
                "msg": (
                    "I could not reach the language model provider right now. "
                    "Please try again in a moment."
                ),
            }


noema_core = NoemaCore()
_ORCHESTRATOR: Orquestador | None = None
_ORCHESTRATOR_CONTEXT: Contexto | None = None

try:
    escalation_model_data = joblib.load("data/models/support_escalation.joblib")
    escalation_model = escalation_model_data["model"]
except Exception:
    escalation_model = None


def _get_orchestrator() -> Orquestador:
    global _ORCHESTRATOR, _ORCHESTRATOR_CONTEXT
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    if not ANALYTICS_DB.exists():
        raise RuntimeError(f"analytics database not found: {ANALYTICS_DB}")
    registry = ToolRegistry()
    for module in (customer_tools, credit_tools, case_tools):
        module.registrar(registry)
    _ORCHESTRATOR_CONTEXT = Contexto(
        analitica=abrir_analitica(str(ANALYTICS_DB)),
        corte=ORCHESTRATOR_CUTOFF,
        politica=Politica.cargar(),
        expedientes=abrir_ledger(LEDGER_DB),
    )
    _ORCHESTRATOR = Orquestador(registry=registry, contexto=_ORCHESTRATOR_CONTEXT)
    return _ORCHESTRATOR


class ChatRequest(BaseModel):
    customer_id: str
    message: str
    history: str = ""
    channel: str = "chatbot"
    interaction_type: str = "inbound"
    reason_category: str = "general_inquiry"
    identity_verified_demo: bool = False


class ChatResponse(BaseModel):
    response: str
    escalate_to_human: bool
    action_taken: str | None = None
    identity_verified_demo: bool = False
    customer_id: str | None = None
    display_name: str | None = None
    segment: str | None = None
    trace: list["AgentTraceStep"] = Field(default_factory=list)


class CustomerProfileResponse(BaseModel):
    customer_id: str
    found: bool
    display_name: str | None = None
    segment: str | None = None
    identity_hint: str | None = None


class AgentTraceStep(BaseModel):
    step: int
    layer: str
    phase: str
    status: str
    title: str
    detail: str
    policy: str
    evidence: str
    databricks_target: str


class DiagnosticCheck(BaseModel):
    name: str
    passed: bool
    expected: str
    observed: str


class PolicyDiagnosticsResponse(BaseModel):
    status: str
    policy_version: int
    checks: list[DiagnosticCheck]


def _dump_model(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


def _display_name(customer: dict) -> str:
    return " ".join(
        part
        for part in (
            str(customer.get("first_name", "")).strip(),
            str(customer.get("last_name", "")).strip(),
        )
        if part
    )


def _session_for_request(request: ChatRequest, customer_id: str | None) -> Session:
    return Session(
        role=Role.CUSTOMER,
        verified=bool(request.identity_verified_demo and customer_id),
        customer_id=customer_id if request.identity_verified_demo else None,
        jti=f"ui-{customer_id or 'anonymous'}",
        conversation_id=f"ui-{customer_id or 'anonymous'}",
    )


def _product_type_from_text(text: str) -> str | None:
    lowered = text.lower()
    aliases = (
        ("Tarjeta Crédito", ("tarjeta", "card", "credit card", "crédito", "credito")),
        ("Préstamo Personal", ("personal", "loan", "préstamo", "prestamo")),
        ("Préstamo Hipotecario", ("hipoteca", "hipotecario", "mortgage")),
    )
    for product, terms in aliases:
        if any(term in lowered for term in terms):
            return product
    return None


def _extract_amount_usd(text: str) -> float | None:
    if not re.search(r"\busd\b|\$|d[oó]lar|dollar", text, flags=re.IGNORECASE):
        return None
    matches = re.findall(r"\d[\d,]*(?:\.\d{1,2})?|\d[\d.]*(?:,\d{1,2})?", text)
    if not matches:
        return None
    raw = matches[0]
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return None
    return amount if amount > 0 else None


def _generate_with_llm(prompt: str) -> str:
    import os

    import requests

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


def _slots_from_message(text: str, intent: str) -> dict:
    import json

    prompt = f"""Extract banking slots from this message for intent: {intent}.
Message: "{text}"
Respond ONLY with a valid JSON object matching this exact schema:
{{"product_type": "Tarjeta Crédito"|"Préstamo Personal"|"Préstamo Hipotecario"|null,
 "requested_amount": float|null, "currency": "USD"|"EUR"|null}}"""
    draft = _generate_with_llm(prompt)
    if draft:
        try:
            parsed = json.loads(draft.strip("` \n").removeprefix("json"))
            return parsed
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                "llm_slot_extraction_failed type=%s", type(e).__name__
            )

    # Fallback
    slots: dict[str, object] = {}
    product_type = _product_type_from_text(text)
    if product_type:
        slots["product_type"] = product_type
    if intent == "CREDIT_ELIGIBILITY":
        amount = _extract_amount_usd(text)
        if amount is not None:
            slots["requested_amount"] = amount
            slots["currency"] = "USD"
    return slots


def _orchestrator_intent(runtime_intent: str) -> str | None:
    if runtime_intent in {"eligibility", "recommendation"}:
        return "CREDIT_ELIGIBILITY"
    if runtime_intent == "products":
        return "PRODUCT_INFO"
    return None


def _format_offer(offer: dict) -> str:
    product = offer.get("producto", "producto")
    amount = offer.get("monto_ofrecido_usd", offer.get("monto_maximo_usd"))
    payment = offer.get("cuota_estimada_usd")
    term = offer.get("plazo_meses")
    tea = offer.get("tea_pct")
    parts = [str(product)]
    if amount is not None:
        parts.append(f"monto hasta ${float(amount):,.2f} USD")
    if term is not None:
        parts.append(f"plazo {int(term)} meses")
    if payment is not None:
        parts.append(f"cuota estimada ${float(payment):,.2f} USD")
    if tea is not None:
        parts.append(f"TEA {float(tea):.2f}%")
    return "; ".join(parts)


def _draft_orchestrated_response(turn: Turno) -> str:
    if turn.desenlace is Desenlace.BLOQUEADO:
        return turn.mensaje
    if turn.desenlace is Desenlace.PREGUNTA:
        missing = set(turn.pregunta_por)
        if {"requested_amount", "currency"} <= missing:
            return (
                "I can check which credit option fits you through the deterministic policy "
                "engine, but I need the amount and currency first. For example: "
                "credit card for $5,000 USD."
            )
        if "requested_amount" in missing:
            return "I need the amount before I can run the policy check."
        if "currency" in missing:
            return "I need the currency before I can run the policy check."
        if "product_type" in missing:
            return "I need the product type before I can run the policy check."
        return "I need one more verified detail before I can run the policy check."
    if turn.desenlace is Desenlace.ESCALADO:
        suffix = f" Caso: {turn.case_id}." if turn.case_id else ""
        return f"{turn.mensaje}{suffix}"
    if turn.ofertas:
        shown = "; ".join(_format_offer(offer) for offer in turn.ofertas[:3])
        if turn.action_id:
            return f"La política verificable dejó esta cotización registrada: {shown}."
        return f"These are the verified options from our eligibility policy: {shown}."
    if turn.decision:
        eligible = "elegible" if turn.decision.get("elegible") else "no elegible"
        reasons = ", ".join(turn.decision.get("motivos", [])[:3])
        return f"La política determinística evaluó el caso como {eligible}. {reasons}".strip()
    return turn.mensaje


def _run_orchestrator_turn(
    request: ChatRequest,
    *,
    effective_customer_id: str | None,
    runtime_intent: str,
    force_human: bool = False,
) -> tuple[Turno, str]:
    orchestrator = _get_orchestrator()
    session = _session_for_request(request, effective_customer_id)
    agent_intent = _orchestrator_intent(runtime_intent) or "CREDIT_ELIGIBILITY"
    slots = _slots_from_message(request.message, agent_intent)
    turn = orchestrator.turno(
        session,
        intencion=agent_intent,
        slots=slots,
        pide_humano=force_human,
    )
    requested_product = slots.get("product_type")
    if requested_product and agent_intent == "CREDIT_ELIGIBILITY" and turn.ofertas:
        turn.ofertas = [
            offer for offer in turn.ofertas if offer.get("producto") == requested_product
        ]

    def redactar(_attempt: int, _previous) -> str:
        context = _draft_orchestrated_response(turn)
        prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response \
to the customer based on this verified system information:
System Information: "{context}"
Customer Message: "{request.message}"
IMPORTANT: Do not invent any numbers. Only use the numbers \
and facts provided in the System Information.
"""
        draft = _generate_with_llm(prompt)
        if draft:
            return draft
        return context

    if turn.desenlace in {Desenlace.RESPUESTA, Desenlace.ESCALADO}:
        turn, verified_text = orchestrator.redactar_y_verificar(turn, session, redactar)
        return turn, verified_text or turn.mensaje
    return turn, _draft_orchestrated_response(turn)


def _trace_from_turn(turn: Turno) -> list[AgentTraceStep]:
    status_by_outcome = {
        Desenlace.RESPUESTA: "achieved",
        Desenlace.PREGUNTA: "pending",
        Desenlace.ESCALADO: "not_achieved",
        Desenlace.BLOQUEADO: "not_achieved",
    }
    trace: list[AgentTraceStep] = []
    for idx, transition in enumerate(turn.etapas, start=1):
        status = status_by_outcome.get(turn.desenlace, "pending")
        if transition.etapa.value in {"IDENTIFY", "UNDERSTAND", "VERIFY"}:
            status = "achieved" if turn.desenlace is not Desenlace.BLOQUEADO else status
        if transition.etapa.value == "ESCALATE":
            status = "achieved" if turn.case_id else "not_achieved"
        trace.append(
            AgentTraceStep(
                step=idx,
                layer="Noema Agent",
                phase=transition.etapa.value.lower(),
                status=status,
                title=f"{transition.etapa.value} via real orchestrator",
                detail=transition.razon,
                policy=(
                    "The GUI chat path is using the production agent orchestrator, "
                    "registered tools, SCM evidence, policy decisions, and verification."
                ),
                evidence=(
                    f"desenlace={turn.desenlace.value}; case_id={turn.case_id or 'none'}; "
                    f"action_id={turn.action_id or 'none'}; "
                    f"epistemic_status={(turn.scm or {}).get('epistemic_status')}"
                ),
                databricks_target="bronze.agent_events",
            )
        )
    return trace


def _write_chat_log(
    request: ChatRequest,
    response: ChatResponse,
    *,
    core_action: str,
    model_escalated: bool,
) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "trace_id": str(uuid.uuid4()),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "event_type": "chat_interaction",
        "customer_id": request.customer_id,
        "channel": request.channel,
        "interaction_type": request.interaction_type,
        "reason_category": request.reason_category,
        "identity_verified_demo_in": request.identity_verified_demo,
        "user_message": request.message,
        "history_chars": len(request.history),
        "assistant_response": response.response,
        "action_taken": response.action_taken,
        "core_action": core_action,
        "escalate_to_human": response.escalate_to_human,
        "model_escalated": model_escalated,
        "identity_verified_demo_out": response.identity_verified_demo,
        "visible_logic_trace": [_dump_model(step) for step in response.trace],
        "private_reasoning_logged": False,
        "databricks_targets": sorted({step.databricks_target for step in response.trace}),
    }
    with TRACE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _policy_diagnostic_checks() -> PolicyDiagnosticsResponse:
    policy = Politica.cargar()
    scenarios = {
        "eligible_customer_gets_offer": Cliente(
            "demo",
            6000,
            "Premium",
            date(2020, 1, 1),
            capacidad_estimada_usd=2500,
        ),
        "missing_income_abstains": Cliente("demo", None, "Premium", date(2020, 1, 1)),
        "missing_obligation_terms_abstain": Cliente(
            "demo",
            6000,
            "Premium",
            date(2020, 1, 1),
            productos=(ProductoVigente("Tarjeta Crédito", None, 30, date(2020, 1, 1)),),
            capacidad_estimada_usd=2500,
        ),
        "missing_capacity_restricts_mortgage": Cliente(
            "demo",
            6000,
            "Premium",
            date(2020, 1, 1),
        ),
    }
    decisions = {name: policy.evaluar(client) for name, client in scenarios.items()}
    checks = [
        DiagnosticCheck(
            name="Eligible verified customer receives at least one policy offer",
            passed=(
                decisions["eligible_customer_gets_offer"].elegible
                and not decisions["eligible_customer_gets_offer"].abstencion
                and bool(decisions["eligible_customer_gets_offer"].productos_elegibles)
            ),
            expected="elegible=true, abstencion=false, offers>0",
            observed=(
                f"elegible={decisions['eligible_customer_gets_offer'].elegible}, "
                f"abstencion={decisions['eligible_customer_gets_offer'].abstencion}, "
                f"offers={len(decisions['eligible_customer_gets_offer'].productos_elegibles)}"
            ),
        ),
        DiagnosticCheck(
            name="Missing income produces abstention",
            passed=(
                decisions["missing_income_abstains"].abstencion
                and not decisions["missing_income_abstains"].elegible
            ),
            expected="abstencion=true, elegible=false",
            observed=(
                f"abstencion={decisions['missing_income_abstains'].abstencion}, "
                f"elegible={decisions['missing_income_abstains'].elegible}"
            ),
        ),
        DiagnosticCheck(
            name="Incomplete current debt terms produce abstention",
            passed=(
                decisions["missing_obligation_terms_abstain"].abstencion
                and not decisions["missing_obligation_terms_abstain"].elegible
            ),
            expected="abstencion=true when existing obligation lacks limit or rate",
            observed=(
                f"abstencion={decisions['missing_obligation_terms_abstain'].abstencion}, "
                f"motivos={len(decisions['missing_obligation_terms_abstain'].motivos)}"
            ),
        ),
        DiagnosticCheck(
            name="Missing observed capacity restricts mortgage offers",
            passed=all(
                offer.producto != "Préstamo Hipotecario"
                for offer in decisions["missing_capacity_restricts_mortgage"].productos_elegibles
            ),
            expected="Préstamo Hipotecario absent from offers",
            observed=(
                "offers="
                + ", ".join(
                    offer.producto
                    for offer in decisions[
                        "missing_capacity_restricts_mortgage"
                    ].productos_elegibles
                )
            ),
        ),
    ]
    return PolicyDiagnosticsResponse(
        status="pass" if all(check.passed for check in checks) else "fail",
        policy_version=policy.version,
        checks=checks,
    )


def _chat_trace(
    request: ChatRequest,
    core_result: dict,
    model_escalated: bool,
    final_escalation: bool,
) -> list[AgentTraceStep]:
    diagnostics = _policy_diagnostic_checks()
    policy_status = "achieved" if diagnostics.status == "pass" else "not_achieved"
    customer_data = get_customer_data(request.customer_id)
    customer_found = bool(customer_data)
    claimed_name = core_result.get("claimed_name")
    identity_match = core_result.get("identity_match")
    if core_result.get("identity_match") is False:
        identity_verified_demo = False
    else:
        identity_verified_demo = bool(
            request.identity_verified_demo or core_result.get("identity_verified_demo", False)
        )
    if identity_verified_demo:
        identity_status = "achieved"
        identity_detail = "Demo identity is verified for this browser session."
    elif identity_match is False:
        identity_status = "not_achieved"
        identity_detail = "The typed name does not verify against the loaded demo profile."
    else:
        identity_status = "pending"
        identity_detail = (
            "The demo keeps customer identity as a fixed local scenario. It does not "
            "treat typed claims as bank verification."
        )
    gemini_configured = bool(
        noema_core.api_key
        and len(noema_core.api_key) >= 10
        and noema_core.api_key != "your_copied_api_key_here"
    )
    provider_attempted = bool(core_result.get("provider_attempted", False))
    provider_failed = core_result["msg"].startswith("I could not reach the language model provider")
    if not provider_attempted:
        provider_status = "pending"
        provider_detail = "The provider was bypassed because deterministic logic handled the turn."
    elif not gemini_configured:
        provider_status = "not_achieved"
        provider_detail = "No valid Gemini key is configured, so generated answers cannot run."
    elif provider_failed:
        provider_status = "not_achieved"
        provider_detail = "The provider call was attempted but did not complete."
    else:
        provider_status = "achieved"
        provider_detail = "The provider call completed and returned text to the API."
    return [
        AgentTraceStep(
            step=1,
            layer="Input",
            phase="input",
            status="achieved" if request.message.strip() else "not_achieved",
            title="Capture user request",
            detail=f"Received {len(request.message.strip())} characters from the chatbot.",
            policy="Input must be explicit before any agent action.",
            evidence="message_present=true" if request.message.strip() else "message_present=false",
            databricks_target="bronze.agent_events",
        ),
        AgentTraceStep(
            step=2,
            layer="Session",
            phase="identity",
            status=identity_status,
            title="Check identity boundary",
            detail=identity_detail,
            policy="A customer cannot self-verify identity through chat text.",
            evidence=(
                f"customer_id={request.customer_id}; "
                f"claimed_name={claimed_name or 'none'}; identity_match={identity_match}; "
                f"identity_verified_demo={identity_verified_demo}"
            ),
            databricks_target="silver.agent_identity_checks",
        ),
        AgentTraceStep(
            step=3,
            layer="Data",
            phase="customer-data",
            status="achieved" if customer_found else "not_achieved",
            title="Load customer facts",
            detail=(
                "Customer profile was found in DuckDB and can ground the response."
                if customer_found
                else "No customer profile was found for this customer ID."
            ),
            policy="Customer-specific answers must come from stored customer facts.",
            evidence=(
                f"found=true; segment={customer_data.get('segment')}; "
                f"balance_usd={customer_data.get('total_balance_usd')}"
                if customer_found
                else "found=false"
            ),
            databricks_target="silver.customer_context",
        ),
        AgentTraceStep(
            step=4,
            layer="Cognition",
            phase="intent",
            status="achieved",
            title="Route intent",
            detail=f"Runtime action selected: {core_result['action']}.",
            policy="The agent must classify the request before response or handoff.",
            evidence=f"action={core_result['action']}",
            databricks_target="silver.agent_intent_trace",
        ),
        AgentTraceStep(
            step=5,
            layer="Safeguard",
            phase="escalation-keyword",
            status="achieved" if core_result["action"] == "escalate" else "not_achieved",
            title="Apply deterministic escalation rule",
            detail=(
                "The message matched deterministic escalation routing."
                if core_result["action"] == "escalate"
                else "No deterministic escalation keyword was matched."
            ),
            policy="Human requests and frustration signals bypass normal LLM response.",
            evidence=f"keyword_escalation={core_result['action'] == 'escalate'}",
            databricks_target="gold.escalation_audit",
        ),
        AgentTraceStep(
            step=6,
            layer="Model",
            phase="escalation-model",
            status="achieved" if model_escalated else "not_achieved",
            title="Apply escalation model",
            detail=(
                "The support-escalation model crossed the handoff threshold."
                if model_escalated
                else "The support-escalation model did not trigger handoff."
            ),
            policy="Escalation model may restrict automation by sending risky cases to a person.",
            evidence=(
                f"model_loaded={escalation_model is not None}; model_escalation={model_escalated}"
            ),
            databricks_target="gold.escalation_audit",
        ),
        AgentTraceStep(
            step=7,
            layer="Policy",
            phase="policy",
            status=policy_status,
            title="Check deterministic credit policy",
            detail=(
                f"{sum(check.passed for check in diagnostics.checks)} of "
                f"{len(diagnostics.checks)} global policy diagnostics passed. "
                "These are policy health checks, not a customer-specific approval."
            ),
            policy="Eligibility is deterministic policy logic, not an LLM decision.",
            evidence=f"policy_version={diagnostics.policy_version}; status={diagnostics.status}",
            databricks_target="gold.policy_diagnostics",
        ),
        AgentTraceStep(
            step=8,
            layer="LLM",
            phase="provider",
            status=provider_status,
            title="Check language-model provider",
            detail=provider_detail,
            policy="Generated text requires an explicitly configured provider.",
            evidence=(
                f"gemini_configured={gemini_configured}; "
                f"provider_attempted={provider_attempted}; provider_failed={provider_failed}"
            ),
            databricks_target="silver.llm_provider_events",
        ),
        AgentTraceStep(
            step=9,
            layer="Verifier",
            phase="grounding",
            status="pending",
            title="Verify grounded response",
            detail=(
                "The demo prompt asks the model to use real customer data, but the main "
                "API does not yet block unsupported generated claims before returning."
            ),
            policy="Numbers and recommendations should be grounded in tools or policy facts.",
            evidence="verifier_not_attached_to_main_api=true",
            databricks_target="gold.grounding_audit",
        ),
        AgentTraceStep(
            step=10,
            layer="Decision",
            phase="safeguard",
            status="achieved" if final_escalation else "not_achieved",
            title="Select final action",
            detail=(
                "The route or escalation model selected human handoff."
                if final_escalation
                else "No escalation trigger crossed the handoff threshold."
            ),
            policy="Escalate frustration, human requests, or high-risk support signals.",
            evidence=(
                f"keyword_escalation={core_result['action'] == 'escalate'}; "
                f"model_escalation={model_escalated}"
            ),
            databricks_target="gold.escalation_audit",
        ),
        AgentTraceStep(
            step=11,
            layer="Observability",
            phase="databricks",
            status="pending",
            title="Prepare Databricks trace event",
            detail=(
                "Each visible trace step is structured so it can be written later to "
                "Databricks as an event row with phase, status, policy, evidence, and target."
            ),
            policy="Operational traces must be structured and auditable.",
            evidence="trace_schema=AgentTraceStep",
            databricks_target="bronze.agent_events",
        ),
    ]


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    core_result = noema_core.process(
        request.message,
        request.history,
        request.customer_id,
        request.identity_verified_demo,
    )

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

    final_escalation = core_result["action"] == "escalate" or escalate
    trace = _chat_trace(request, core_result, escalate, final_escalation)
    if core_result.get("identity_match") is False:
        identity_verified_demo = False
    else:
        identity_verified_demo = bool(
            request.identity_verified_demo or core_result.get("identity_verified_demo", False)
        )
    effective_customer_id = core_result.get("verified_customer_id") or request.customer_id
    customer = get_customer_data(effective_customer_id) if effective_customer_id else {}
    display_name = core_result.get("verified_display_name") or _display_name(customer) or None
    segment = core_result.get("verified_segment") or customer.get("segment")

    orchestrated_intent = _orchestrator_intent(noema_core.scm.evaluate(request.message)["intent"])
    should_orchestrate = bool(orchestrated_intent) or core_result["action"] == "escalate"
    if should_orchestrate:
        try:
            turn, agent_response = _run_orchestrator_turn(
                request,
                effective_customer_id=effective_customer_id,
                runtime_intent=noema_core.scm.evaluate(request.message)["intent"],
                force_human=core_result["action"] == "escalate",
            )
            trace = _trace_from_turn(turn)
            action_taken = (
                "escalation" if turn.desenlace is Desenlace.ESCALADO else "real_orchestrator"
            )
            response = ChatResponse(
                response=agent_response,
                escalate_to_human=turn.desenlace is Desenlace.ESCALADO,
                action_taken=action_taken,
                identity_verified_demo=identity_verified_demo,
                customer_id=effective_customer_id,
                display_name=display_name if identity_verified_demo else None,
                segment=segment if identity_verified_demo else None,
                trace=trace,
            )
            _write_chat_log(
                request,
                response,
                core_action=core_result["action"],
                model_escalated=escalate,
            )
            return response
        except Exception as exc:
            LOGGER.exception("real_orchestrator_failed type=%s", type(exc).__name__)
            trace = [
                AgentTraceStep(
                    step=1,
                    layer="Noema Agent",
                    phase="runtime",
                    status="not_achieved",
                    title="Real orchestrator unavailable",
                    detail=(
                        "The GUI attempted to use the production agent orchestrator, "
                        f"but the backend could not complete the turn: {type(exc).__name__}."
                    ),
                    policy="The GUI must fail closed when the real agent cannot run.",
                    evidence="orchestrator_integration_attempted=true",
                    databricks_target="bronze.agent_events",
                )
            ]
            response = ChatResponse(
                response=(
                    "No pude completar el turno con el orquestador real. Me abstengo "
                    "de dar una decisión bancaria y puedo derivarte con un asesor."
                ),
                escalate_to_human=True,
                action_taken="orchestrator_unavailable",
                identity_verified_demo=identity_verified_demo,
                customer_id=effective_customer_id,
                display_name=display_name if identity_verified_demo else None,
                segment=segment if identity_verified_demo else None,
                trace=trace,
            )
            _write_chat_log(
                request,
                response,
                core_action=core_result["action"],
                model_escalated=escalate,
            )
            return response

    if final_escalation:
        response = ChatResponse(
            response=(
                "I am transferring you to a human expert who can better assist you right away."
            ),
            escalate_to_human=True,
            action_taken="escalation",
            identity_verified_demo=identity_verified_demo,
            customer_id=effective_customer_id,
            display_name=display_name if identity_verified_demo else None,
            segment=segment if identity_verified_demo else None,
            trace=trace,
        )
        _write_chat_log(
            request,
            response,
            core_action=core_result["action"],
            model_escalated=escalate,
        )
        return response

    final_msg = core_result["msg"]
    prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response \
to the customer based on this verified system information:
System Information: "{final_msg}"
Customer Message: "{request.message}"
RULES:
1. Rephrase the system information into a natural, friendly reply.
2. Do NOT mention the phrase "System Information".
3. ONLY use the numbers provided in the system information.
4. NEVER repeat unverified numbers from the customer.
"""
    draft = _generate_with_llm(prompt)
    if draft:
        final_msg = draft

    response = ChatResponse(
        response=final_msg,
        escalate_to_human=False,
        action_taken=core_result["action"],
        identity_verified_demo=identity_verified_demo,
        customer_id=effective_customer_id,
        display_name=display_name if identity_verified_demo else None,
        segment=segment if identity_verified_demo else None,
        trace=trace,
    )
    _write_chat_log(
        request,
        response,
        core_action=core_result["action"],
        model_escalated=escalate,
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/customer-profile/{customer_id}", response_model=CustomerProfileResponse)
def customer_profile(customer_id: str):
    customer = get_customer_data(customer_id)
    if not customer:
        return CustomerProfileResponse(customer_id=customer_id, found=False)
    display_name = _display_name(customer)
    return CustomerProfileResponse(
        customer_id=customer_id,
        found=True,
        display_name=display_name,
        segment=customer.get("segment"),
        identity_hint=f"my name is {display_name}",
    )


@app.get("/api/policy-diagnostics", response_model=PolicyDiagnosticsResponse)
def policy_diagnostics():
    return _policy_diagnostic_checks()
