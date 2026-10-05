
# --- CHUNK ---
Created At: 2026-10-02T23:19:18-06:00
Completed At: 2026-10-02T23:19:18-06:00
File Path: `file:///Users/federicovargas/Documents/factored-hackathon-2026-noema/api/main.py`
Total Lines: 1350
Total Bytes: 52265
Showing lines 1 to 800
The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
1: import json
2: import logging
3: import os
4: import re
5: import uuid
6: from datetime import UTC, date, datetime
7: from pathlib import Path
8:
9: import duckdb
10: import joblib
11: import pandas as pd
12: import requests
13: from dotenv import load_dotenv
14: from fastapi import FastAPI
15: from fastapi.middleware.cors import CORSMiddleware
16: from pydantic import BaseModel, Field
17:
18: from agent.core.orchestrator import Desenlace, Orquestador, Turno
19: from agent.policies.engine import Cliente, Politica, ProductoVigente
20: from agent.tools import cases as case_tools
21: from agent.tools import credit as credit_tools
22: from agent.tools import customer as customer_tools
23: from agent.tools.ledger import abrir_ledger
24: from agent.tools.registry import Role, Session, ToolRegistry
25: from agent.tools.store import Contexto, abrir_analitica
26:
27: load_dotenv()
28:
29: LOGGER = logging.getLogger(__name__)
30: TRACE_DIR = Path("logs/traces")
31: TRACE_FILE = TRACE_DIR / "chat_interactions.jsonl"
32: ANALYTICS_DB = Path(os.getenv("NOEMA_ANALYTICS_DB", "data/noema.duckdb"))
33: LEDGER_DB = os.getenv("NOEMA_LEDGER_DB", "data/noema_ledger.duckdb")
34: ORCHESTRATOR_CUTOFF = date(2025, 12, 31)
35:
36: app = FastAPI(title="Noema AI-First Banking Core", version="1.0.0")
37:
38: app.add_middleware(
39:     CORSMiddleware,
40:     allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
41:     allow_credentials=True,
42:     allow_methods=["*"],
43:     allow_headers=["*"],
44: )
45:
46:
47: class SemanticCognitionMatrix:
48:     def evaluate(self, text: str) -> dict:
49:         text = text.lower()
50:         if any(
51:             term in text
52:             for term in (
53:                 "angry",
54:                 "asesor",
55:                 "atendente",
56:                 "frustrated",
57:                 "human",
58:                 "humano",
59:                 "persona",
60:                 "escalate",
61:             )
62:         ):
63:             return {"intent": "escalation"}
64:         if any(term in text for term in ("balance", "saldo", "balances")):
65:             return {"intent": "balance"}
66:         if any(
67:             term in text
68:             for term in (
69:                 "monthly income",
70:                 "montly income",
71:                 "income",
72:                 "ingreso mensual",
73:                 "ingreso",
74:             )
75:         ):
76:             return {"intent": "income"}
77:         if any(
78:             term in text
79:             for term in (
80:                 "what can you do",
81:                 "help me with",
82:                 "capabilities",
83:                 "que puedes hacer",
84:                 "qué puedes hacer",
85:             )
86:         ):
87:             return {"intent": "capabilities"}
88:         if any(
89:             term in text
90:             for term in ("recommend", "recommendation", "recomienda", "recomendar")
91:         ):
92:             return {"intent": "recommendation"}
93:         if re.search(
94:             r"\b(best|mejor|which|cu[aá]l|suitable|conviene|for me|para m[ií])\b",
95:             text,
96:         ) and any(term in text for term in ("card", "tarjeta", "credit", "crédito", "credito")):
97:             return {"intent": "recommendation"}
98:         if any(
99:             term in text
100:             for term in (
101:                 "obligation",
102:                 "obligacion",
103:                 "obligación",
104:                 "capacity",
105:                 "capacidad",
106:                 "terms",
107:                 "options",
108:                 "opciones",
109:             )
110:         ):
111:             return {"intent": "financial_profile"}
112:         if any(term in text for term in ("eligible", "eligib", "loan", "credito", "crédito")):
113:             return {"intent": "eligibility"}
114:         if any(term in text for term in ("product", "producto", "card", "tarjeta")):
115:             return {"intent": "products"}
116:         if re.search(r"\b(i am|i'm|my name is|soy|me llamo)\b", text):
117:             return {"intent": "identity_claim"}
118:         return {"intent": "unknown"}
119:
120:
121: def _normalizar_nombre(value: str) -> str:
122:     return re.sub(r"\s+", " ", value.strip().lower())
123:
124:
125: def _extract_claimed_name(text: str) -> str | None:
126:     match = re.search(
127:         r"\b(?:i am|i'm|my name is|soy|me llamo)\s+(.+)$",
128:         text.strip(),
129:         flags=re.IGNORECASE,
130:     )
131:     if not match:
132:         return None
133:     claimed = re.split(r"[,.!?;:]", match.group(1), maxsplit=1)[0]
134:     return claimed.strip() or None
135:
136:
137: def get_customer_data(customer_id: str) -> dict:
138:     try:
139:         with duckdb.connect("data/noema.duckdb", read_only=True) as con:
140:             df = con.execute(
141:                 """
142:                 SELECT first_name, last_name, country, segment, total_balance_usd,
143:                        estimated_monthly_income, days_past_due
144:                 FROM noema_gold.customer_360
145:                 WHERE customer_id = ?
146:                 """,
147:                 [customer_id],
148:             ).df()
149:         if not df.empty:
150:             return df.to_dict("records")[0]
151:     except Exception as e:
152:         LOGGER.warning("customer_lookup_failed type=%s", type(e).__name__)
153:     return {}
154:
155:
156: def find_customer_by_name(full_name: str | None) -> dict:
157:     if not full_name:
158:         return {}
159:     normalized_claim = _normalizar_nombre(full_name)
160:     try:
161:         with duckdb.connect("data/noema.duckdb", read_only=True) as con:
162:             df = con.execute(
163:                 """
164:                 SELECT customer_id, first_name, last_name, country, segment, total_balance_usd,
165:                        estimated_monthly_income, days_past_due
166:                 FROM noema_gold.customer_360
167:                 """,
168:             ).df()
169:         if df.empty:
170:             return {}
171:         df["full_name"] = (
172:             df["first_name"].fillna("").astype(str).str.strip()
173:             + " "
174:             + df["last_name"].fillna("").astype(str).str.strip()
175:         )
176:         matches = df[df["full_name"].map(_normalizar_nombre) == normalized_claim]
177:         if not matches.empty:
178:             return matches.iloc[0].to_dict()
179:     except Exception as e:
180:         LOGGER.warning("customer_name_lookup_failed type=%s", type(e).__name__)
181:     return {}
182:
183:
184: def get_customer_products(customer_id: str) -> list[dict]:
185:     if not customer_id:
186:         return []
187:     try:
188:         with duckdb.connect("data/noema.duckdb", read_only=True) as con:
189:             df = con.execute(
190:                 """
191:                 SELECT product_id, product_type, currency, current_balance, credit_limit,
192:                        interest_rate, product_status, days_past_due
193:                 FROM noema_silver.stg_products
194:                 WHERE customer_id = ?
195:                   AND product_status = 'Active'
196:                 ORDER BY product_type, product_id
197:                 """,
198:                 [customer_id],
199:             ).df()
200:         return df.to_dict("records")
201:     except Exception as e:
202:         LOGGER.warning("customer_products_lookup_failed type=%s", type(e).__name__)
203:     return []
204:
205:
206: def _product_catalog_names() -> str:
207:     return ", ".join(item["producto"] for item in Politica.cargar().catalogo)
208:
209:
210: def _credit_card_terms() -> dict:
211:     for item in Politica.cargar().catalogo:
212:         if item["producto"] == "Tarjeta Crédito":
213:             return item
214:     return {}
215:
216:
217: def _financial_profile_message(
218:     customer: dict,
219:     products: list[dict],
220:     identity_verified_demo: bool,
221: ) -> str:
222:     if not identity_verified_demo:
223:         return (
224:             "I need to verify the demo identity before showing income, obligations, "
225:             "capacity, or card options. Type: my name is <your full name>."
226:         )
227:     if not customer:
228:         return (
229:             "I cannot find a verified customer profile for this demo session, so I will not "
230:             "invent income, obligations, capacity, or card options."
231:         )
232:
233:     first_name = customer.get("first_name", "there")
234:     segment = customer.get("segment") or "unknown"
235:     income = customer.get("estimated_monthly_income")
236:     balance = float(customer.get("total_balance_usd") or 0)
237:     credit_product_types = {
238:         "Tarjeta Crédito",
239:         "Préstamo Personal",
240:         "Préstamo Hipotecario",
241:     }
242:     active_credit = [
243:         product
244:         for product in products
245:         if product.get("product_type") in credit_product_types
246:     ]
247:     active_deposit = [
248:         product
249:         for product in products
250:         if product.get("product_type") not in credit_product_types
251:     ]
252:     card = _credit_card_terms()
253:     income_text = (
254:         f"${float(income):,.2f} monthly estimated income"
255:         if income is not None
256:         else "no estimated monthly income value in the loaded profile"
257:     )
258:     credit_obligation_text = (
259:         f"{len(active_credit)} active credit obligation(s)"
260:         if active_credit
261:         else "no active credit obligations found in the active product records"
262:     )
263:     capacity_text = (
264:         "capacity is not fully computed in the main chatbot yet; the deterministic "
265:         "eligibility engine still needs verified credit-product details and policy evaluation"
266:     )
267:     card_terms = (
268:         f"Tarjeta Crédito is available to segments {', '.join(card.get('segmentos', []))}; "
269:         f"catalog range ${float(card.get('monto_minimo_usd', 0)):,.0f}-"
270:         f"${float(card.get('monto_maximo_usd', 0)):,.0f} USD; "
271:         f"annual rate {float(card.get('tasa_anual', 0)):.2f}%; "
272:         f"amortization={card.get('amortizacion', 'unknown')}."
273:         if card
274:         else "Tarjeta Crédito terms were not found in the policy catalog."
275:     )
276:     segment_fit = (
277:         "Your Plus segment is within the catalog segment list for Tarjeta Crédito."
278:         if segment in set(card.get("segmentos", []))
279:         else "Your segment is not in the catalog segment list for Tarjeta Crédito."
280:     )
281:     return (
282:         f"{first_name}, here are the verified inputs I can show: income={income_text}; "
283:         f"segment={segment}; recorded total balance=${balance:,.2f} USD; "
284:         f"active deposit/account products={len(active_deposit)}; "
285:         f"obligations={credit_obligation_text}; "
286:         f"capacity={capacity_text}. For credit-card options: {card_terms} {segment_fit} "
287:         "This is not an approval or final recommendation; it is the grounded input summary "
288:         "needed before the policy engine can make an eligibility decision."
289:     )
290:
291:
292: def _income_message(customer: dict, identity_verified_demo: bool) -> str:
293:     if not identity_verified_demo:
294:         return (
295:             "I need to verify the demo identity before showing income. "
296:             "Type: my name is <your full name>."
297:         )
298:     if not customer:
299:         return "I cannot find a verified customer profile, so I will not invent income."
300:     income = customer.get("estimated_monthly_income")
301:     first_name = customer.get("first_name", "this customer")
302:     country = customer.get("country") or "the source profile"
303:     if income is None:
304:         return f"I do not have an estimated monthly income value for {first_name}."
305:     return (
306:         f"{first_name}'s estimated monthly income is {float(income):,.2f} "
307:         f"in the source customer profile for {country}. This field is not the USD "
308:         "balance; it is the stored income estimate from the customer record."
309:     )
310:
311:
312: def _capabilities_message(identity_verified_demo: bool) -> str:
313:     identity_note = (
314:         "I can use Sandra's verified demo profile."
315:         if identity_verified_demo
316:         else "First verify the demo identity by typing: my name is <your full name>."
317:     )
318:     return (
319:         f"{identity_note} I can show balance, estimated income, segment, active products, "
320:         "and product catalog details. I can also run our eligibility policy check "
321:         "for credit options when you give a product, amount, and currency."
322:     )
323:
324:
325: def _recommendation_message(customer: dict, identity_verified_demo: bool) -> str:
326:     if not identity_verified_demo:
327:         return (
328:             "I need to verify the demo identity before making account-specific suggestions. "
329:             "Type: my name is <your full name>."
330:         )
331:     if not customer:
332:         return (
333:             "I cannot find a verified customer profile for this demo session, so I will not "
334:             "invent a recommendation."
335:         )
336:     first_name = customer.get("first_name", "there")
337:     balance = float(customer.get("total_balance_usd") or 0)
338:     segment = customer.get("segment") or "unknown"
339:     days_past_due = customer.get("days_past_due")
340:     catalog = _product_catalog_names()
341:     delinquency_note = (
342:         f"The profile shows {days_past_due:.0f} days past due, so the safest next step is to "
343:         "resolve the overdue status before exploring new credit."
344:         if days_past_due is not None and float(days_past_due) > 0
345:         else "I do not see an overdue-days flag in the loaded profile, so the safe next step is "
346:         "to review available products without treating them as approved offers."
347:     )
348:     return (
349:         f"{first_name}, based on the verified local profile I can see segment={segment} and "
350:         f"recorded balance=${balance:,.2f} USD. {delinquency_note} The current policy catalog "
351:         f"contains: {catalog}. My practical recommendation is to ask for the product catalog "
352:         "or a policy eligibility check next; I will not claim you are approved until the "
353:         "deterministic eligibility engine evaluates the required facts."
354:     )
355:
356:
357: class NoemaCore:
358:     def __init__(self):
359:         self.scm = SemanticCognitionMatrix()
360:         self.api_key = os.getenv("GEMINI_API_KEY")
361:
362:     def process(
363:         self,
364:         query: str,
365:         history: str,
366:         customer_id: str,
367:         identity_verified_demo: bool = False,
368:     ) -> dict:
369:         scm_result = self.scm.evaluate(query)
370:         intent = scm_result["intent"]
371:
372:         if intent == "escalation":
373:             return {
374:                 "action": "escalate",
375:                 "provider_attempted": False,
376:                 "msg": (
377:                     "I understand your frustration. I am transferring you to a human "
378:                     "expert right now."
379:                 ),
380:             }
381:
382:         cust_data = get_customer_data(customer_id)
383:         products = get_customer_products(customer_id)
384:         if intent == "balance":
385:             if not identity_verified_demo:
386:                 return {
387:                     "action": "abstain",
388:                     "provider_attempted": False,
389:                     "identity_verified_demo": False,
390:                     "msg": (
391:                         "I need to verify the demo identity before showing account "
392:                         "balances. Type: my name is <your full name>."
393:                     ),
394:                 }
395:             if not cust_data:
396:                 return {
397:                     "action": "abstain",
398:                     "provider_attempted": False,
399:                     "identity_verified_demo": identity_verified_demo,
400:                     "msg": (
401:                         "I cannot find a verified customer profile for this demo customer ID, "
402:                         "so I will not invent a balance."
403:                     ),
404:                 }
405:             return {
406:                 "action": "respond",
407:                 "provider_attempted": False,
408:                 "identity_verified_demo": identity_verified_demo,
409:                     "msg": (
410:                         f"For {cust_data.get('first_name', 'this customer')}, the recorded total "
411:                         f"balance is ${cust_data.get('total_balance_usd', 0):,.2f} USD. "
412:                         "This comes from the local DuckDB customer_360 table."
413:                     ),
414:                 }
415:
416:         if intent == "income":
417:             return {
418:                 "action": "respond",
419:                 "provider_attempted": False,
420:                 "identity_verified_demo": identity_verified_demo,
421:                 "msg": _income_message(cust_data, identity_verified_demo),
422:             }
423:
424:         if intent == "identity_claim":
425:             claimed_name = _extract_claimed_name(query)
426:             matched_customer = find_customer_by_name(claimed_name)
427:             stored_name = _display_name(matched_customer)
428:             if not matched_customer:
429:                 return {
430:                     "action": "abstain",
431:                     "provider_attempted": False,
432:                     "claimed_name": claimed_name,
433:                     "identity_match": False,
434:                     "identity_verified_demo": False,
435:                     "msg": (
436:                         f"I cannot verify the name '{claimed_name}'. Please check the full "
437:                         "name and try again."
438:                     ),
439:                 }
440:             if claimed_name and _normalizar_nombre(claimed_name) == _normalizar_nombre(stored_name):
441:                 return {
442:                     "action": "verify_identity",
443:                     "provider_attempted": False,
444:                     "claimed_name": claimed_name,
445:                     "identity_match": True,
446:                     "identity_verified_demo": True,
447:                     "verified_customer_id": matched_customer.get("customer_id"),
448:                     "verified_display_name": stored_name,
449:                     "verified_segment": matched_customer.get("segment"),
450:                     "msg": (
451:                         f"Demo identity verified for {stored_name}. You can now ask for "
452:                         "account facts available in this local demo."
453:                     ),
454:                 }
455:             return {
456:                 "action": "abstain",
457:                 "provider_attempted": False,
458:                 "claimed_name": claimed_name,
459:                 "identity_match": False,
460:                 "identity_verified_demo": False,
461:                 "msg": (
462:                     f"I cannot verify the name '{claimed_name}'. Please check the full "
463:                     "name and try again."
464:                 ),
465:             }
466:
467:         if intent == "eligibility":
468:             return {
469:                 "action": "abstain",
470:                 "provider_attempted": False,
471:                 "identity_verified_demo": identity_verified_demo,
472:                 "msg": (
473:                     _financial_profile_message(cust_data, products, identity_verified_demo)
474:                     + " Ask me to run a policy eligibility check once that route is connected "
475:                     "to the live UI action."
476:                 ),
477:             }
478:
479:         if intent == "financial_profile":
480:             return {
481:                 "action": "respond",
482:                 "provider_attempted": False,
483:                 "identity_verified_demo": identity_verified_demo,
484:                 "msg": _financial_profile_message(cust_data, products, identity_verified_demo),
485:             }
486:
487:         if intent == "capabilities":
488:             return {
489:                 "action": "respond",
490:                 "provider_attempted": False,
491:                 "identity_verified_demo": identity_verified_demo,
492:                 "msg": _capabilities_message(identity_verified_demo),
493:             }
494:
495:         if intent == "recommendation":
496:             return {
497:                 "action": "respond",
498:                 "provider_attempted": False,
499:                 "identity_verified_demo": identity_verified_demo,
500:                 "msg": _recommendation_message(cust_data, identity_verified_demo),
501:             }
502:
503:         if intent == "products":
504:             catalog = _product_catalog_names()
505:             return {
506:                 "action": "respond",
507:                 "provider_attempted": False,
508:                 "identity_verified_demo": identity_verified_demo,
509:                 "msg": (
510:                     "The versioned policy catalog contains these products: "
511:                     f"{catalog}. These are not offers until the policy engine evaluates "
512:                     "verified customer facts."
513:                 ),
514:             }
515:
516:         return {
517:             "action": "abstain",
518:             "provider_attempted": False,
519:             "identity_verified_demo": identity_verified_demo,
520:             "msg": (
521:                 "I do not have a grounded tool-backed answer for that request yet. "
522:                 "I will not guess or invent banking information."
523:             ),
524:         }
525:
526:     def generate_with_llm(self, query: str, history: str, customer_id: str) -> dict:
527:         if not self.api_key or len(self.api_key) < 10 or self.api_key == "your_copied_api_key_here":
528:             return {
529:                 "action": "abstain",
530:                 "provider_attempted": False,
531:                 "msg": "No valid language-model provider is configured.",
532:             }
533:         try:
534:             url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={self.api_key}"
535:             payload = {"contents": [{"parts": [{"text": query + "\n" + history}]}]}
536:             res = requests.post(url, json=payload, timeout=20)
537:             data = res.json()
538:             text_response = data["candidates"][0]["content"]["parts"][0]["text"]
539:             return {"action": "respond", "provider_attempted": True, "msg": text_response}
540:         except Exception as e:
541:             LOGGER.warning("llm_call_failed type=%s", type(e).__name__)
542:             return {
543:                 "action": "abstain",
544:                 "provider_attempted": True,
545:                 "msg": (
546:                     "I could not reach the language model provider right now. "
547:                     "Please try again in a moment."
548:                 ),
549:             }
550:
551:
552: noema_core = NoemaCore()
553: _ORCHESTRATOR: Orquestador | None = None
554: _ORCHESTRATOR_CONTEXT: Contexto | None = None
555:
556: try:
557:     escalation_model_data = joblib.load("data/models/support_escalation.joblib")
558:     escalation_model = escalation_model_data["model"]
559: except Exception:
560:     escalation_model = None
561:
562:
563: def _get_orchestrator() -> Orquestador:
564:     global _ORCHESTRATOR, _ORCHESTRATOR_CONTEXT
565:     if _ORCHESTRATOR is not None:
566:         return _ORCHESTRATOR
567:     if not ANALYTICS_DB.exists():
568:         raise RuntimeError(f"analytics database not found: {ANALYTICS_DB}")
569:     registry = ToolRegistry()
570:     for module in (customer_tools, credit_tools, case_tools):
571:         module.registrar(registry)
572:     _ORCHESTRATOR_CONTEXT = Contexto(
573:         analitica=abrir_analitica(str(ANALYTICS_DB)),
574:         corte=ORCHESTRATOR_CUTOFF,
575:         politica=Politica.cargar(),
576:         expedientes=abrir_ledger(LEDGER_DB),
577:     )
578:     _ORCHESTRATOR = Orquestador(registry=registry, contexto=_ORCHESTRATOR_CONTEXT)
579:     return _ORCHESTRATOR
580:
581:
582: class ChatRequest(BaseModel):
583:     customer_id: str
584:     message: str
585:     history: str = ""
586:     channel: str = "chatbot"
587:     interaction_type: str = "inbound"
588:     reason_category: str = "general_inquiry"
589:     identity_verified_demo: bool = False
590:
591:
592: class ChatResponse(BaseModel):
593:     response: str
594:     escalate_to_human: bool
595:     action_taken: str | None = None
596:     identity_verified_demo: bool = False
597:     customer_id: str | None = None
598:     display_name: str | None = None
599:     segment: str | None = None
600:     trace: list["AgentTraceStep"] = Field(default_factory=list)
601:
602:
603: class CustomerProfileResponse(BaseModel):
604:     customer_id: str
605:     found: bool
606:     display_name: str | None = None
607:     segment: str | None = None
608:     identity_hint: str | None = None
609:
610:
611: class AgentTraceStep(BaseModel):
612:     step: int
613:     layer: str
614:     phase: str
615:     status: str
616:     title: str
617:     detail: str
618:     policy: str
619:     evidence: str
620:     databricks_target: str
621:
622:
623: class DiagnosticCheck(BaseModel):
624:     name: str
625:     passed: bool
626:     expected: str
627:     observed: str
628:
629:
630: class PolicyDiagnosticsResponse(BaseModel):
631:     status: str
632:     policy_version: int
633:     checks: list[DiagnosticCheck]
634:
635:
636: def _dump_model(model: BaseModel) -> dict:
637:     return model.model_dump(mode="json")
638:
639:
640: def _display_name(customer: dict) -> str:
641:     return " ".join(
642:         part
643:         for part in (
644:             str(customer.get("first_name", "")).strip(),
645:             str(customer.get("last_name", "")).strip(),
646:         )
647:         if part
648:     )
649:
650:
651: def _session_for_request(request: ChatRequest, customer_id: str | None) -> Session:
652:     return Session(
653:         role=Role.CUSTOMER,
654:         verified=bool(request.identity_verified_demo and customer_id),
655:         customer_id=customer_id if request.identity_verified_demo else None,
656:         jti=f"ui-{customer_id or 'anonymous'}",
657:         conversation_id=f"ui-{customer_id or 'anonymous'}",
658:     )
659:
660:
661: def _product_type_from_text(text: str) -> str | None:
662:     lowered = text.lower()
663:     aliases = (
664:         ("Tarjeta Crédito", ("tarjeta", "card", "credit card", "crédito", "credito")),
665:         ("Préstamo Personal", ("personal", "loan", "préstamo", "prestamo")),
666:         ("Préstamo Hipotecario", ("hipoteca", "hipotecario", "mortgage")),
667:     )
668:     for product, terms in aliases:
669:         if any(term in lowered for term in terms):
670:             return product
671:     return None
672:
673:
674: def _extract_amount_usd(text: str) -> float | None:
675:     if not re.search(r"\busd\b|\$|d[oó]lar|dollar", text, flags=re.IGNORECASE):
676:         return None
677:     matches = re.findall(r"\d[\d,]*(?:\.\d{1,2})?|\d[\d.]*(?:,\d{1,2})?", text)
678:     if not matches:
679:         return None
680:     raw = matches[0]
681:     if "," in raw and "." in raw:
682:         raw = raw.replace(",", "")
683:     elif "," in raw:
684:         raw = raw.replace(",", ".")
685:     try:
686:         amount = float(raw)
687:     except ValueError:
688:         return None
689:     return amount if amount > 0 else None
690:
691:
692: def _slots_from_message(text: str, intent: str) -> dict:
693:     slots: dict[str, object] = {}
694:     product_type = _product_type_from_text(text)
695:     if product_type:
696:         slots["product_type"] = product_type
697:     if intent == "CREDIT_ELIGIBILITY":
698:         amount = _extract_amount_usd(text)
699:         if amount is not None:
700:             slots["requested_amount"] = amount
701:             slots["currency"] = "USD"
702:     return slots
703:
704:
705: def _orchestrator_intent(runtime_intent: str) -> str | None:
706:     if runtime_intent in {"eligibility", "recommendation"}:
707:         return "CREDIT_ELIGIBILITY"
708:     if runtime_intent == "products":
709:         return "PRODUCT_INFO"
710:     return None
711:
712:
713: def _format_offer(offer: dict) -> str:
714:     product = offer.get("producto", "producto")
715:     amount = offer.get("monto_ofrecido_usd", offer.get("monto_maximo_usd"))
716:     payment = offer.get("cuota_estimada_usd")
717:     term = offer.get("plazo_meses")
718:     tea = offer.get("tea_pct")
719:     parts = [str(product)]
720:     if amount is not None:
721:         parts.append(f"monto hasta ${float(amount):,.2f} USD")
722:     if term is not None:
723:         parts.append(f"plazo {int(term)} meses")
724:     if payment is not None:
725:         parts.append(f"cuota estimada ${float(payment):,.2f} USD")
726:     if tea is not None:
727:         parts.append(f"TEA {float(tea):.2f}%")
728:     return "; ".join(parts)
729:
730:
731: def _draft_orchestrated_response(turn: Turno) -> str:
732:     if turn.desenlace is Desenlace.BLOQUEADO:
733:         return turn.mensaje
734:     if turn.desenlace is Desenlace.PREGUNTA:
735:         missing = set(turn.pregunta_por)
736:         if {"requested_amount", "currency"} <= missing:
737:             return (
738:                 "I can check which credit option fits you through the deterministic policy "
739:                 "engine, but I need the amount and currency first. For example: "
740:                 "credit card for $5,000 USD."
741:             )
742:         if "requested_amount" in missing:
743:             return "I need the amount before I can run the policy check."
744:         if "currency" in missing:
745:             return "I need the currency before I can run the policy check."
746:         if "product_type" in missing:
747:             return "I need the product type before I can run the policy check."
748:         return "I need one more verified detail before I can run the policy check."
749:     if turn.desenlace is Desenlace.ESCALADO:
750:         suffix = f" Caso: {turn.case_id}." if turn.case_id else ""
751:         return f"{turn.mensaje}{suffix}"
752:     if turn.ofertas:
753:         shown = "; ".join(_format_offer(offer) for offer in turn.ofertas[:3])
754:         if turn.action_id:
755:             return f"La política verificable dejó esta cotización registrada: {shown}."
756:         return f"These are the verified options from our eligibility policy: {shown}."
757:     if turn.decision:
758:         eligible = "elegible" if turn.decision.get("elegible") else "no elegible"
759:         reasons = ", ".join(turn.decision.get("motivos", [])[:3])
760:         return f"La política determinística evaluó el caso como {eligible}. {reasons}".strip()
761:     return turn.mensaje
762:
763:
764: def _run_orchestrator_turn(
765:     request: ChatRequest,
766:     *,
767:     effective_customer_id: str | None,
768:     runtime_intent: str,
769:     force_human: bool = False,
770: ) -> tuple[Turno, str]:
771:     orchestrator = _get_orchestrator()
772:     session = _session_for_request(request, effective_customer_id)
773:     agent_intent = _orchestrator_intent(runtime_intent) or "CREDIT_ELIGIBILITY"
774:     slots = _slots_from_message(request.message, agent_intent)
775:     turn = orchestrator.turno(
776:         session,
777:         intencion=agent_intent,
778:         slots=slots,
779:         pide_humano=force_human,
780:     )
781:     requested_product = slots.get("product_type")
782:     if requested_product and agent_intent == "CREDIT_ELIGIBILITY" and turn.ofertas:
783:         turn.ofertas = [
784:             offer for offer in turn.ofertas if offer.get("producto") == requested_product
785:         ]
786:
787:     def redactar(_attempt: int, _previous) -> str:
788:         return _draft_orchestrated_response(turn)
789:
790:     if turn.desenlace in {Desenlace.RESPUESTA, Desenlace.ESCALADO}:
791:         turn, verified_text = orchestrator.redactar_y_verificar(turn, session, redactar)
792:         return turn, verified_text or turn.mensaje
793:     return turn, _draft_orchestrated_response(turn)
794:
795:
796: def _trace_from_turn(turn: Turno) -> list[AgentTraceStep]:
797:     status_by_outcome = {
798:         Desenlace.RESPUESTA: "achieved",
799:         Desenlace.PREGUNTA: "pending",
800:         Desenlace.ESCALADO: "not_achieved",
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

# --- CHUNK ---
Created At: 2026-10-02T23:19:33-06:00
Completed At: 2026-10-02T23:19:33-06:00
File Path: `file:///Users/federicovargas/Documents/factored-hackathon-2026-noema/api/main.py`
Total Lines: 1350
Total Bytes: 52265
Showing lines 801 to 1350
The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
801:         Desenlace.BLOQUEADO: "not_achieved",
802:     }
803:     trace: list[AgentTraceStep] = []
804:     for idx, transition in enumerate(turn.etapas, start=1):
805:         status = status_by_outcome.get(turn.desenlace, "pending")
806:         if transition.etapa.value in {"IDENTIFY", "UNDERSTAND", "VERIFY"}:
807:             status = "achieved" if turn.desenlace is not Desenlace.BLOQUEADO else status
808:         if transition.etapa.value == "ESCALATE":
809:             status = "achieved" if turn.case_id else "not_achieved"
810:         trace.append(
811:             AgentTraceStep(
812:                 step=idx,
813:                 layer="Noema Agent",
814:                 phase=transition.etapa.value.lower(),
815:                 status=status,
816:                 title=f"{transition.etapa.value} via real orchestrator",
817:                 detail=transition.razon,
818:                 policy=(
819:                     "The GUI chat path is using the production agent orchestrator, "
820:                     "registered tools, SCM evidence, policy decisions, and verification."
821:                 ),
822:                 evidence=(
823:                     f"desenlace={turn.desenlace.value}; case_id={turn.case_id or 'none'}; "
824:                     f"action_id={turn.action_id or 'none'}; "
825:                     f"epistemic_status={(turn.scm or {}).get('epistemic_status')}"
826:                 ),
827:                 databricks_target="bronze.agent_events",
828:             )
829:         )
830:     return trace
831:
832:
833: def _write_chat_log(
834:     request: ChatRequest,
835:     response: ChatResponse,
836:     *,
837:     core_action: str,
838:     model_escalated: bool,
839: ) -> None:
840:     TRACE_DIR.mkdir(parents=True, exist_ok=True)
841:     record = {
842:         "trace_id": str(uuid.uuid4()),
843:         "timestamp_utc": datetime.now(UTC).isoformat(),
844:         "event_type": "chat_interaction",
845:         "customer_id": request.customer_id,
846:         "channel": request.channel,
847:         "interaction_type": request.interaction_type,
848:         "reason_category": request.reason_category,
849:         "identity_verified_demo_in": request.identity_verified_demo,
850:         "user_message": request.message,
851:         "history_chars": len(request.history),
852:         "assistant_response": response.response,
853:         "action_taken": response.action_taken,
854:         "core_action": core_action,
855:         "escalate_to_human": response.escalate_to_human,
856:         "model_escalated": model_escalated,
857:         "identity_verified_demo_out": response.identity_verified_demo,
858:         "visible_logic_trace": [_dump_model(step) for step in response.trace],
859:         "private_reasoning_logged": False,
860:         "databricks_targets": sorted({step.databricks_target for step in response.trace}),
861:     }
862:     with TRACE_FILE.open("a", encoding="utf-8") as handle:
863:         handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
864:
865:
866: def _policy_diagnostic_checks() -> PolicyDiagnosticsResponse:
867:     policy = Politica.cargar()
868:     scenarios = {
869:         "eligible_customer_gets_offer": Cliente(
870:             "demo",
871:             6000,
872:             "Premium",
873:             date(2020, 1, 1),
874:             capacidad_estimada_usd=2500,
875:         ),
876:         "missing_income_abstains": Cliente("demo", None, "Premium", date(2020, 1, 1)),
877:         "missing_obligation_terms_abstain": Cliente(
878:             "demo",
879:             6000,
880:             "Premium",
881:             date(2020, 1, 1),
882:             productos=(ProductoVigente("Tarjeta Crédito", None, 30, date(2020, 1, 1)),),
883:             capacidad_estimada_usd=2500,
884:         ),
885:         "missing_capacity_restricts_mortgage": Cliente(
886:             "demo",
887:             6000,
888:             "Premium",
889:             date(2020, 1, 1),
890:         ),
891:     }
892:     decisions = {name: policy.evaluar(client) for name, client in scenarios.items()}
893:     checks = [
894:         DiagnosticCheck(
895:             name="Eligible verified customer receives at least one policy offer",
896:             passed=(
897:                 decisions["eligible_customer_gets_offer"].elegible
898:                 and not decisions["eligible_customer_gets_offer"].abstencion
899:                 and bool(decisions["eligible_customer_gets_offer"].productos_elegibles)
900:             ),
901:             expected="elegible=true, abstencion=false, offers>0",
902:             observed=(
903:                 f"elegible={decisions['eligible_customer_gets_offer'].elegible}, "
904:                 f"abstencion={decisions['eligible_customer_gets_offer'].abstencion}, "
905:                 f"offers={len(decisions['eligible_customer_gets_offer'].productos_elegibles)}"
906:             ),
907:         ),
908:         DiagnosticCheck(
909:             name="Missing income produces abstention",
910:             passed=(
911:                 decisions["missing_income_abstains"].abstencion
912:                 and not decisions["missing_income_abstains"].elegible
913:             ),
914:             expected="abstencion=true, elegible=false",
915:             observed=(
916:                 f"abstencion={decisions['missing_income_abstains'].abstencion}, "
917:                 f"elegible={decisions['missing_income_abstains'].elegible}"
918:             ),
919:         ),
920:         DiagnosticCheck(
921:             name="Incomplete current debt terms produce abstention",
922:             passed=(
923:                 decisions["missing_obligation_terms_abstain"].abstencion
924:                 and not decisions["missing_obligation_terms_abstain"].elegible
925:             ),
926:             expected="abstencion=true when existing obligation lacks limit or rate",
927:             observed=(
928:                 f"abstencion={decisions['missing_obligation_terms_abstain'].abstencion}, "
929:                 f"motivos={len(decisions['missing_obligation_terms_abstain'].motivos)}"
930:             ),
931:         ),
932:         DiagnosticCheck(
933:             name="Missing observed capacity restricts mortgage offers",
934:             passed=all(
935:                 offer.producto != "Préstamo Hipotecario"
936:                 for offer in decisions["missing_capacity_restricts_mortgage"].productos_elegibles
937:             ),
938:             expected="Préstamo Hipotecario absent from offers",
939:             observed=(
940:                 "offers="
941:                 + ", ".join(
942:                     offer.producto
943:                     for offer in decisions[
944:                         "missing_capacity_restricts_mortgage"
945:                     ].productos_elegibles
946:                 )
947:             ),
948:         ),
949:     ]
950:     return PolicyDiagnosticsResponse(
951:         status="pass" if all(check.passed for check in checks) else "fail",
952:         policy_version=policy.version,
953:         checks=checks,
954:     )
955:
956:
957: def _chat_trace(
958:     request: ChatRequest,
959:     core_result: dict,
960:     model_escalated: bool,
961:     final_escalation: bool,
962: ) -> list[AgentTraceStep]:
963:     diagnostics = _policy_diagnostic_checks()
964:     policy_status = "achieved" if diagnostics.status == "pass" else "not_achieved"
965:     customer_data = get_customer_data(request.customer_id)
966:     customer_found = bool(customer_data)
967:     claimed_name = core_result.get("claimed_name")
968:     identity_match = core_result.get("identity_match")
969:     if core_result.get("identity_match") is False:
970:         identity_verified_demo = False
971:     else:
972:         identity_verified_demo = bool(
973:             request.identity_verified_demo or core_result.get("identity_verified_demo", False)
974:         )
975:     if identity_verified_demo:
976:         identity_status = "achieved"
977:         identity_detail = "Demo identity is verified for this browser session."
978:     elif identity_match is False:
979:         identity_status = "not_achieved"
980:         identity_detail = "The typed name does not verify against the loaded demo profile."
981:     else:
982:         identity_status = "pending"
983:         identity_detail = (
984:             "The demo keeps customer identity as a fixed local scenario. It does not "
985:             "treat typed claims as bank verification."
986:         )
987:     gemini_configured = bool(
988:         noema_core.api_key
989:         and len(noema_core.api_key) >= 10
990:         and noema_core.api_key != "your_copied_api_key_here"
991:     )
992:     provider_attempted = bool(core_result.get("provider_attempted", False))
993:     provider_failed = core_result["msg"].startswith("I could not reach the language model provider")
994:     if not provider_attempted:
995:         provider_status = "pending"
996:         provider_detail = (
997:             "The provider was bypassed because deterministic logic handled the turn."
998:         )
999:     elif not gemini_configured:
1000:         provider_status = "not_achieved"
1001:         provider_detail = "No valid Gemini key is configured, so generated answers cannot run."
1002:     elif provider_failed:
1003:         provider_status = "not_achieved"
1004:         provider_detail = "The provider call was attempted but did not complete."
1005:     else:
1006:         provider_status = "achieved"
1007:         provider_detail = "The provider call completed and returned text to the API."
1008:     return [
1009:         AgentTraceStep(
1010:             step=1,
1011:             layer="Input",
1012:             phase="input",
1013:             status="achieved" if request.message.strip() else "not_achieved",
1014:             title="Capture user request",
1015:             detail=f"Received {len(request.message.strip())} characters from the chatbot.",
1016:             policy="Input must be explicit before any agent action.",
1017:             evidence="message_present=true" if request.message.strip() else "message_present=false",
1018:             databricks_target="bronze.agent_events",
1019:         ),
1020:         AgentTraceStep(
1021:             step=2,
1022:             layer="Session",
1023:             phase="identity",
1024:             status=identity_status,
1025:             title="Check identity boundary",
1026:             detail=identity_detail,
1027:             policy="A customer cannot self-verify identity through chat text.",
1028:             evidence=(
1029:                 f"customer_id={request.customer_id}; "
1030:                 f"claimed_name={claimed_name or 'none'}; identity_match={identity_match}; "
1031:                 f"identity_verified_demo={identity_verified_demo}"
1032:             ),
1033:             databricks_target="silver.agent_identity_checks",
1034:         ),
1035:         AgentTraceStep(
1036:             step=3,
1037:             layer="Data",
1038:             phase="customer-data",
1039:             status="achieved" if customer_found else "not_achieved",
1040:             title="Load customer facts",
1041:             detail=(
1042:                 "Customer profile was found in DuckDB and can ground the response."
1043:                 if customer_found
1044:                 else "No customer profile was found for this customer ID."
1045:             ),
1046:             policy="Customer-specific answers must come from stored customer facts.",
1047:             evidence=(
1048:                 f"found=true; segment={customer_data.get('segment')}; "
1049:                 f"balance_usd={customer_data.get('total_balance_usd')}"
1050:                 if customer_found
1051:                 else "found=false"
1052:             ),
1053:             databricks_target="silver.customer_context",
1054:         ),
1055:         AgentTraceStep(
1056:             step=4,
1057:             layer="Cognition",
1058:             phase="intent",
1059:             status="achieved",
1060:             title="Route intent",
1061:             detail=f"Runtime action selected: {core_result['action']}.",
1062:             policy="The agent must classify the request before response or handoff.",
1063:             evidence=f"action={core_result['action']}",
1064:             databricks_target="silver.agent_intent_trace",
1065:         ),
1066:         AgentTraceStep(
1067:             step=5,
1068:             layer="Safeguard",
1069:             phase="escalation-keyword",
1070:             status="achieved" if core_result["action"] == "escalate" else "not_achieved",
1071:             title="Apply deterministic escalation rule",
1072:             detail=(
1073:                 "The message matched deterministic escalation routing."
1074:                 if core_result["action"] == "escalate"
1075:                 else "No deterministic escalation keyword was matched."
1076:             ),
1077:             policy="Human requests and frustration signals bypass normal LLM response.",
1078:             evidence=f"keyword_escalation={core_result['action'] == 'escalate'}",
1079:             databricks_target="gold.escalation_audit",
1080:         ),
1081:         AgentTraceStep(
1082:             step=6,
1083:             layer="Model",
1084:             phase="escalation-model",
1085:             status="achieved" if model_escalated else "not_achieved",
1086:             title="Apply escalation model",
1087:             detail=(
1088:                 "The support-escalation model crossed the handoff threshold."
1089:                 if model_escalated
1090:                 else "The support-escalation model did not trigger handoff."
1091:             ),
1092:             policy="Escalation model may restrict automation by sending risky cases to a person.",
1093:             evidence=(
1094:                 f"model_loaded={escalation_model is not None}; "
1095:                 f"model_escalation={model_escalated}"
1096:             ),
1097:             databricks_target="gold.escalation_audit",
1098:         ),
1099:         AgentTraceStep(
1100:             step=7,
1101:             layer="Policy",
1102:             phase="policy",
1103:             status=policy_status,
1104:             title="Check deterministic credit policy",
1105:             detail=(
1106:                 f"{sum(check.passed for check in diagnostics.checks)} of "
1107:                 f"{len(diagnostics.checks)} global policy diagnostics passed. "
1108:                 "These are policy health checks, not a customer-specific approval."
1109:             ),
1110:             policy="Eligibility is deterministic policy logic, not an LLM decision.",
1111:             evidence=f"policy_version={diagnostics.policy_version}; status={diagnostics.status}",
1112:             databricks_target="gold.policy_diagnostics",
1113:         ),
1114:         AgentTraceStep(
1115:             step=8,
1116:             layer="LLM",
1117:             phase="provider",
1118:             status=provider_status,
1119:             title="Check language-model provider",
1120:             detail=provider_detail,
1121:             policy="Generated text requires an explicitly configured provider.",
1122:             evidence=(
1123:                 f"gemini_configured={gemini_configured}; "
1124:                 f"provider_attempted={provider_attempted}; provider_failed={provider_failed}"
1125:             ),
1126:             databricks_target="silver.llm_provider_events",
1127:         ),
1128:         AgentTraceStep(
1129:             step=9,
1130:             layer="Verifier",
1131:             phase="grounding",
1132:             status="pending",
1133:             title="Verify grounded response",
1134:             detail=(
1135:                 "The demo prompt asks the model to use real customer data, but the main "
1136:                 "API does not yet block unsupported generated claims before returning."
1137:             ),
1138:             policy="Numbers and recommendations should be grounded in tools or policy facts.",
1139:             evidence="verifier_not_attached_to_main_api=true",
1140:             databricks_target="gold.grounding_audit",
1141:         ),
1142:         AgentTraceStep(
1143:             step=10,
1144:             layer="Decision",
1145:             phase="safeguard",
1146:             status="achieved" if final_escalation else "not_achieved",
1147:             title="Select final action",
1148:             detail=(
1149:                 "The route or escalation model selected human handoff."
1150:                 if final_escalation
1151:                 else "No escalation trigger crossed the handoff threshold."
1152:             ),
1153:             policy="Escalate frustration, human requests, or high-risk support signals.",
1154:             evidence=(
1155:                 f"keyword_escalation={core_result['action'] == 'escalate'}; "
1156:                 f"model_escalation={model_escalated}"
1157:             ),
1158:             databricks_target="gold.escalation_audit",
1159:         ),
1160:         AgentTraceStep(
1161:             step=11,
1162:             layer="Observability",
1163:             phase="databricks",
1164:             status="pending",
1165:             title="Prepare Databricks trace event",
1166:             detail=(
1167:                 "Each visible trace step is structured so it can be written later to "
1168:                 "Databricks as an event row with phase, status, policy, evidence, and target."
1169:             ),
1170:             policy="Operational traces must be structured and auditable.",
1171:             evidence="trace_schema=AgentTraceStep",
1172:             databricks_target="bronze.agent_events",
1173:         ),
1174:     ]
1175:
1176:
1177: @app.post("/api/chat", response_model=ChatResponse)
1178: async def chat_endpoint(request: ChatRequest):
1179:     core_result = noema_core.process(
1180:         request.message,
1181:         request.history,
1182:         request.customer_id,
1183:         request.identity_verified_demo,
1184:     )
1185:
1186:     escalate = False
1187:     if escalation_model and core_result["action"] != "escalate":
1188:         df = pd.DataFrame(
1189:             [
1190:                 {
1191:                     "channel": request.channel,
1192:                     "interaction_type": request.interaction_type,
1193:                     "reason_category": request.reason_category,
1194:                 }
1195:             ]
1196:         )
1197:         prob = escalation_model.predict_proba(df)[0][1]
1198:         if prob > 0.5:
1199:             escalate = True
1200:
1201:     final_escalation = core_result["action"] == "escalate" or escalate
1202:     trace = _chat_trace(request, core_result, escalate, final_escalation)
1203:     if core_result.get("identity_match") is False:
1204:         identity_verified_demo = False
1205:     else:
1206:         identity_verified_demo = bool(
1207:             request.identity_verified_demo or core_result.get("identity_verified_demo", False)
1208:         )
1209:     effective_customer_id = core_result.get("verified_customer_id") or request.customer_id
1210:     customer = get_customer_data(effective_customer_id) if effective_customer_id else {}
1211:     display_name = core_result.get("verified_display_name") or _display_name(customer) or None
1212:     segment = core_result.get("verified_segment") or customer.get("segment")
1213:
1214:     orchestrated_intent = _orchestrator_intent(noema_core.scm.evaluate(request.message)["intent"])
1215:     should_orchestrate = bool(orchestrated_intent) or core_result["action"] == "escalate"
1216:     if should_orchestrate:
1217:         try:
1218:             turn, agent_response = _run_orchestrator_turn(
1219:                 request,
1220:                 effective_customer_id=effective_customer_id,
1221:                 runtime_intent=noema_core.scm.evaluate(request.message)["intent"],
1222:                 force_human=core_result["action"] == "escalate",
1223:             )
1224:             trace = _trace_from_turn(turn)
1225:             action_taken = (
1226:                 "escalation"
1227:                 if turn.desenlace is Desenlace.ESCALADO
1228:                 else "real_orchestrator"
1229:             )
1230:             response = ChatResponse(
1231:                 response=agent_response,
1232:                 escalate_to_human=turn.desenlace is Desenlace.ESCALADO,
1233:                 action_taken=action_taken,
1234:                 identity_verified_demo=identity_verified_demo,
1235:                 customer_id=effective_customer_id,
1236:                 display_name=display_name if identity_verified_demo else None,
1237:                 segment=segment if identity_verified_demo else None,
1238:                 trace=trace,
1239:             )
1240:             _write_chat_log(
1241:                 request,
1242:                 response,
1243:                 core_action=core_result["action"],
1244:                 model_escalated=escalate,
1245:             )
1246:             return response
1247:         except Exception as exc:
1248:             LOGGER.exception("real_orchestrator_failed type=%s", type(exc).__name__)
1249:             trace = [
1250:                 AgentTraceStep(
1251:                     step=1,
1252:                     layer="Noema Agent",
1253:                     phase="runtime",
1254:                     status="not_achieved",
1255:                     title="Real orchestrator unavailable",
1256:                     detail=(
1257:                         "The GUI attempted to use the production agent orchestrator, "
1258:                         f"but the backend could not complete the turn: {type(exc).__name__}."
1259:                     ),
1260:                     policy="The GUI must fail closed when the real agent cannot run.",
1261:                     evidence="orchestrator_integration_attempted=true",
1262:                     databricks_target="bronze.agent_events",
1263:                 )
1264:             ]
1265:             response = ChatResponse(
1266:                 response=(
1267:                     "No pude completar el turno con el orquestador real. Me abstengo "
1268:                     "de dar una decisión bancaria y puedo derivarte con un asesor."
1269:                 ),
1270:                 escalate_to_human=True,
1271:                 action_taken="orchestrator_unavailable",
1272:                 identity_verified_demo=identity_verified_demo,
1273:                 customer_id=effective_customer_id,
1274:                 display_name=display_name if identity_verified_demo else None,
1275:                 segment=segment if identity_verified_demo else None,
1276:                 trace=trace,
1277:             )
1278:             _write_chat_log(
1279:                 request,
1280:                 response,
1281:                 core_action=core_result["action"],
1282:                 model_escalated=escalate,
1283:             )
1284:             return response
1285:
1286:     if final_escalation:
1287:         response = ChatResponse(
1288:             response=(
1289:                 "I am transferring you to a human expert who can better assist you "
1290:                 "right away."
1291:             ),
1292:             escalate_to_human=True,
1293:             action_taken="escalation",
1294:             identity_verified_demo=identity_verified_demo,
1295:             customer_id=effective_customer_id,
1296:             display_name=display_name if identity_verified_demo else None,
1297:             segment=segment if identity_verified_demo else None,
1298:             trace=trace,
1299:         )
1300:         _write_chat_log(
1301:             request,
1302:             response,
1303:             core_action=core_result["action"],
1304:             model_escalated=escalate,
1305:         )
1306:         return response
1307:
1308:     response = ChatResponse(
1309:         response=core_result["msg"],
1310:         escalate_to_human=False,
1311:         action_taken=core_result["action"],
1312:         identity_verified_demo=identity_verified_demo,
1313:         customer_id=effective_customer_id,
1314:         display_name=display_name if identity_verified_demo else None,
1315:         segment=segment if identity_verified_demo else None,
1316:         trace=trace,
1317:     )
1318:     _write_chat_log(
1319:         request,
1320:         response,
1321:         core_action=core_result["action"],
1322:         model_escalated=escalate,
1323:     )
1324:     return response
1325:
1326:
1327: @app.get("/health")
1328: def health():
1329:     return {"status": "ok"}
1330:
1331:
1332: @app.get("/api/customer-profile/{customer_id}", response_model=CustomerProfileResponse)
1333: def customer_profile(customer_id: str):
1334:     customer = get_customer_data(customer_id)
1335:     if not customer:
1336:         return CustomerProfileResponse(customer_id=customer_id, found=False)
1337:     display_name = _display_name(customer)
1338:     return CustomerProfileResponse(
1339:         customer_id=customer_id,
1340:         found=True,
1341:         display_name=display_name,
1342:         segment=customer.get("segment"),
1343:         identity_hint=f"my name is {display_name}",
1344:     )
1345:
1346:
1347: @app.get("/api/policy-diagnostics", response_model=PolicyDiagnosticsResponse)
1348: def policy_diagnostics():
1349:     return _policy_diagnostic_checks()
1350:
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

# --- CHUNK ---
Created At: 2026-10-02T23:22:10-06:00
Completed At: 2026-10-02T23:22:10-06:00
File Path: `file:///Users/federicovargas/Documents/factored-hackathon-2026-noema/api/main.py`
Total Lines: 1350
Total Bytes: 52265
Showing lines 650 to 800
The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
650:
651: def _session_for_request(request: ChatRequest, customer_id: str | None) -> Session:
652:     return Session(
653:         role=Role.CUSTOMER,
654:         verified=bool(request.identity_verified_demo and customer_id),
655:         customer_id=customer_id if request.identity_verified_demo else None,
656:         jti=f"ui-{customer_id or 'anonymous'}",
657:         conversation_id=f"ui-{customer_id or 'anonymous'}",
658:     )
659:
660:
661: def _product_type_from_text(text: str) -> str | None:
662:     lowered = text.lower()
663:     aliases = (
664:         ("Tarjeta Crédito", ("tarjeta", "card", "credit card", "crédito", "credito")),
665:         ("Préstamo Personal", ("personal", "loan", "préstamo", "prestamo")),
666:         ("Préstamo Hipotecario", ("hipoteca", "hipotecario", "mortgage")),
667:     )
668:     for product, terms in aliases:
669:         if any(term in lowered for term in terms):
670:             return product
671:     return None
672:
673:
674: def _extract_amount_usd(text: str) -> float | None:
675:     if not re.search(r"\busd\b|\$|d[oó]lar|dollar", text, flags=re.IGNORECASE):
676:         return None
677:     matches = re.findall(r"\d[\d,]*(?:\.\d{1,2})?|\d[\d.]*(?:,\d{1,2})?", text)
678:     if not matches:
679:         return None
680:     raw = matches[0]
681:     if "," in raw and "." in raw:
682:         raw = raw.replace(",", "")
683:     elif "," in raw:
684:         raw = raw.replace(",", ".")
685:     try:
686:         amount = float(raw)
687:     except ValueError:
688:         return None
689:     return amount if amount > 0 else None
690:
691:
692: def _slots_from_message(text: str, intent: str) -> dict:
693:     slots: dict[str, object] = {}
694:     product_type = _product_type_from_text(text)
695:     if product_type:
696:         slots["product_type"] = product_type
697:     if intent == "CREDIT_ELIGIBILITY":
698:         amount = _extract_amount_usd(text)
699:         if amount is not None:
700:             slots["requested_amount"] = amount
701:             slots["currency"] = "USD"
702:     return slots
703:
704:
705: def _orchestrator_intent(runtime_intent: str) -> str | None:
706:     if runtime_intent in {"eligibility", "recommendation"}:
707:         return "CREDIT_ELIGIBILITY"
708:     if runtime_intent == "products":
709:         return "PRODUCT_INFO"
710:     return None
711:
712:
713: def _format_offer(offer: dict) -> str:
714:     product = offer.get("producto", "producto")
715:     amount = offer.get("monto_ofrecido_usd", offer.get("monto_maximo_usd"))
716:     payment = offer.get("cuota_estimada_usd")
717:     term = offer.get("plazo_meses")
718:     tea = offer.get("tea_pct")
719:     parts = [str(product)]
720:     if amount is not None:
721:         parts.append(f"monto hasta ${float(amount):,.2f} USD")
722:     if term is not None:
723:         parts.append(f"plazo {int(term)} meses")
724:     if payment is not None:
725:         parts.append(f"cuota estimada ${float(payment):,.2f} USD")
726:     if tea is not None:
727:         parts.append(f"TEA {float(tea):.2f}%")
728:     return "; ".join(parts)
729:
730:
731: def _draft_orchestrated_response(turn: Turno) -> str:
732:     if turn.desenlace is Desenlace.BLOQUEADO:
733:         return turn.mensaje
734:     if turn.desenlace is Desenlace.PREGUNTA:
735:         missing = set(turn.pregunta_por)
736:         if {"requested_amount", "currency"} <= missing:
737:             return (
738:                 "I can check which credit option fits you through the deterministic policy "
739:                 "engine, but I need the amount and currency first. For example: "
740:                 "credit card for $5,000 USD."
741:             )
742:         if "requested_amount" in missing:
743:             return "I need the amount before I can run the policy check."
744:         if "currency" in missing:
745:             return "I need the currency before I can run the policy check."
746:         if "product_type" in missing:
747:             return "I need the product type before I can run the policy check."
748:         return "I need one more verified detail before I can run the policy check."
749:     if turn.desenlace is Desenlace.ESCALADO:
750:         suffix = f" Caso: {turn.case_id}." if turn.case_id else ""
751:         return f"{turn.mensaje}{suffix}"
752:     if turn.ofertas:
753:         shown = "; ".join(_format_offer(offer) for offer in turn.ofertas[:3])
754:         if turn.action_id:
755:             return f"La política verificable dejó esta cotización registrada: {shown}."
756:         return f"These are the verified options from our eligibility policy: {shown}."
757:     if turn.decision:
758:         eligible = "elegible" if turn.decision.get("elegible") else "no elegible"
759:         reasons = ", ".join(turn.decision.get("motivos", [])[:3])
760:         return f"La política determinística evaluó el caso como {eligible}. {reasons}".strip()
761:     return turn.mensaje
762:
763:
764: def _run_orchestrator_turn(
765:     request: ChatRequest,
766:     *,
767:     effective_customer_id: str | None,
768:     runtime_intent: str,
769:     force_human: bool = False,
770: ) -> tuple[Turno, str]:
771:     orchestrator = _get_orchestrator()
772:     session = _session_for_request(request, effective_customer_id)
773:     agent_intent = _orchestrator_intent(runtime_intent) or "CREDIT_ELIGIBILITY"
774:     slots = _slots_from_message(request.message, agent_intent)
775:     turn = orchestrator.turno(
776:         session,
777:         intencion=agent_intent,
778:         slots=slots,
779:         pide_humano=force_human,
780:     )
781:     requested_product = slots.get("product_type")
782:     if requested_product and agent_intent == "CREDIT_ELIGIBILITY" and turn.ofertas:
783:         turn.ofertas = [
784:             offer for offer in turn.ofertas if offer.get("producto") == requested_product
785:         ]
786:
787:     def redactar(_attempt: int, _previous) -> str:
788:         return _draft_orchestrated_response(turn)
789:
790:     if turn.desenlace in {Desenlace.RESPUESTA, Desenlace.ESCALADO}:
791:         turn, verified_text = orchestrator.redactar_y_verificar(turn, session, redactar)
792:         return turn, verified_text or turn.mensaje
793:     return turn, _draft_orchestrated_response(turn)
794:
795:
796: def _trace_from_turn(turn: Turno) -> list[AgentTraceStep]:
797:     status_by_outcome = {
798:         Desenlace.RESPUESTA: "achieved",
799:         Desenlace.PREGUNTA: "pending",
800:         Desenlace.ESCALADO: "not_achieved",
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

# --- CHUNK ---
Created At: 2026-10-02T23:26:18-06:00
Completed At: 2026-10-02T23:26:18-06:00
File Path: `file:///Users/federicovargas/Documents/factored-hackathon-2026-noema/api/main.py`
Total Lines: 1407
Total Bytes: 55053
Showing lines 1177 to 1326
The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
1177:             detail=provider_detail,
1178:             policy="Generated text requires an explicitly configured provider.",
1179:             evidence=(
1180:                 f"gemini_configured={gemini_configured}; "
1181:                 f"provider_attempted={provider_attempted}; provider_failed={provider_failed}"
1182:             ),
1183:             databricks_target="silver.llm_provider_events",
1184:         ),
1185:         AgentTraceStep(
1186:             step=9,
1187:             layer="Verifier",
1188:             phase="grounding",
1189:             status="pending",
1190:             title="Verify grounded response",
1191:             detail=(
1192:                 "The demo prompt asks the model to use real customer data, but the main "
1193:                 "API does not yet block unsupported generated claims before returning."
1194:             ),
1195:             policy="Numbers and recommendations should be grounded in tools or policy facts.",
1196:             evidence="verifier_not_attached_to_main_api=true",
1197:             databricks_target="gold.grounding_audit",
1198:         ),
1199:         AgentTraceStep(
1200:             step=10,
1201:             layer="Decision",
1202:             phase="safeguard",
1203:             status="achieved" if final_escalation else "not_achieved",
1204:             title="Select final action",
1205:             detail=(
1206:                 "The route or escalation model selected human handoff."
1207:                 if final_escalation
1208:                 else "No escalation trigger crossed the handoff threshold."
1209:             ),
1210:             policy="Escalate frustration, human requests, or high-risk support signals.",
1211:             evidence=(
1212:                 f"keyword_escalation={core_result['action'] == 'escalate'}; "
1213:                 f"model_escalation={model_escalated}"
1214:             ),
1215:             databricks_target="gold.escalation_audit",
1216:         ),
1217:         AgentTraceStep(
1218:             step=11,
1219:             layer="Observability",
1220:             phase="databricks",
1221:             status="pending",
1222:             title="Prepare Databricks trace event",
1223:             detail=(
1224:                 "Each visible trace step is structured so it can be written later to "
1225:                 "Databricks as an event row with phase, status, policy, evidence, and target."
1226:             ),
1227:             policy="Operational traces must be structured and auditable.",
1228:             evidence="trace_schema=AgentTraceStep",
1229:             databricks_target="bronze.agent_events",
1230:         ),
1231:     ]
1232:
1233:
1234: @app.post("/api/chat", response_model=ChatResponse)
1235: async def chat_endpoint(request: ChatRequest):
1236:     core_result = noema_core.process(
1237:         request.message,
1238:         request.history,
1239:         request.customer_id,
1240:         request.identity_verified_demo,
1241:     )
1242:
1243:     escalate = False
1244:     if escalation_model and core_result["action"] != "escalate":
1245:         df = pd.DataFrame(
1246:             [
1247:                 {
1248:                     "channel": request.channel,
1249:                     "interaction_type": request.interaction_type,
1250:                     "reason_category": request.reason_category,
1251:                 }
1252:             ]
1253:         )
1254:         prob = escalation_model.predict_proba(df)[0][1]
1255:         if prob > 0.5:
1256:             escalate = True
1257:
1258:     final_escalation = core_result["action"] == "escalate" or escalate
1259:     trace = _chat_trace(request, core_result, escalate, final_escalation)
1260:     if core_result.get("identity_match") is False:
1261:         identity_verified_demo = False
1262:     else:
1263:         identity_verified_demo = bool(
1264:             request.identity_verified_demo or core_result.get("identity_verified_demo", False)
1265:         )
1266:     effective_customer_id = core_result.get("verified_customer_id") or request.customer_id
1267:     customer = get_customer_data(effective_customer_id) if effective_customer_id else {}
1268:     display_name = core_result.get("verified_display_name") or _display_name(customer) or None
1269:     segment = core_result.get("verified_segment") or customer.get("segment")
1270:
1271:     orchestrated_intent = _orchestrator_intent(noema_core.scm.evaluate(request.message)["intent"])
1272:     should_orchestrate = bool(orchestrated_intent) or core_result["action"] == "escalate"
1273:     if should_orchestrate:
1274:         try:
1275:             turn, agent_response = _run_orchestrator_turn(
1276:                 request,
1277:                 effective_customer_id=effective_customer_id,
1278:                 runtime_intent=noema_core.scm.evaluate(request.message)["intent"],
1279:                 force_human=core_result["action"] == "escalate",
1280:             )
1281:             trace = _trace_from_turn(turn)
1282:             action_taken = (
1283:                 "escalation"
1284:                 if turn.desenlace is Desenlace.ESCALADO
1285:                 else "real_orchestrator"
1286:             )
1287:             response = ChatResponse(
1288:                 response=agent_response,
1289:                 escalate_to_human=turn.desenlace is Desenlace.ESCALADO,
1290:                 action_taken=action_taken,
1291:                 identity_verified_demo=identity_verified_demo,
1292:                 customer_id=effective_customer_id,
1293:                 display_name=display_name if identity_verified_demo else None,
1294:                 segment=segment if identity_verified_demo else None,
1295:                 trace=trace,
1296:             )
1297:             _write_chat_log(
1298:                 request,
1299:                 response,
1300:                 core_action=core_result["action"],
1301:                 model_escalated=escalate,
1302:             )
1303:             return response
1304:         except Exception as exc:
1305:             LOGGER.exception("real_orchestrator_failed type=%s", type(exc).__name__)
1306:             trace = [
1307:                 AgentTraceStep(
1308:                     step=1,
1309:                     layer="Noema Agent",
1310:                     phase="runtime",
1311:                     status="not_achieved",
1312:                     title="Real orchestrator unavailable",
1313:                     detail=(
1314:                         "The GUI attempted to use the production agent orchestrator, "
1315:                         f"but the backend could not complete the turn: {type(exc).__name__}."
1316:                     ),
1317:                     policy="The GUI must fail closed when the real agent cannot run.",
1318:                     evidence="orchestrator_integration_attempted=true",
1319:                     databricks_target="bronze.agent_events",
1320:                 )
1321:             ]
1322:             response = ChatResponse(
1323:                 response=(
1324:                     "No pude completar el turno con el orquestador real. Me abstengo "
1325:                     "de dar una decisión bancaria y puedo derivarte con un asesor."
1326:                 ),
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

# --- CHUNK ---
Created At: 2026-10-02T23:29:44-06:00
Completed At: 2026-10-02T23:29:45-06:00

The command exited with code 0.
Output:
<truncated 1364 lines>
+    )

     escalate = False
     if escalation_model and core_result["action"] != "escalate":
@@ -161,18 +1255,176 @@ async def chat_endpoint(request: ChatRequest):
         if prob > 0.5:
             escalate = True

-    if core_result["action"] == "escalate" or escalate:
-        return ChatResponse(
-            response="I am transferring you to a human expert who can better assist you right away.",
+    final_escalation = core_result["action"] == "escalate" or escalate
+    trace = _chat_trace(request, core_result, escalate, final_escalation)
+    if core_result.get("identity_match") is False:
+        identity_verified_demo = False
+    else:
+        identity_verified_demo = bool(
+            request.identity_verified_demo or core_result.get("identity_verified_demo", False)
+        )
+    effective_customer_id = core_result.get("verified_customer_id") or request.customer_id
+    customer = get_customer_data(effective_customer_id) if effective_customer_id else {}
+    display_name = core_result.get("verified_display_name") or _display_name(customer) or None
+    segment = core_result.get("verified_segment") or customer.get("segment")
+
+    orchestrated_intent = _orchestrator_intent(noema_core.scm.evaluate(request.message)["intent"])
+    should_orchestrate = bool(orchestrated_intent) or core_result["action"] == "escalate"
+    if should_orchestrate:
+        try:
+            turn, agent_response = _run_orchestrator_turn(
+                request,
+                effective_customer_id=effective_customer_id,
+                runtime_intent=noema_core.scm.evaluate(request.message)["intent"],
+                force_human=core_result["action"] == "escalate",
+            )
+            trace = _trace_from_turn(turn)
+            action_taken = (
+                "escalation"
+                if turn.desenlace is Desenlace.ESCALADO
+                else "real_orchestrator"
+            )
+            response = ChatResponse(
+                response=agent_response,
+                escalate_to_human=turn.desenlace is Desenlace.ESCALADO,
+                action_taken=action_taken,
+                identity_verified_demo=identity_verified_demo,
+                customer_id=effective_customer_id,
+                display_name=display_name if identity_verified_demo else None,
+                segment=segment if identity_verified_demo else None,
+                trace=trace,
+            )
+            _write_chat_log(
+                request,
+                response,
+                core_action=core_result["action"],
+                model_escalated=escalate,
+            )
+            return response
+        except Exception as exc:
+            LOGGER.exception("real_orchestrator_failed type=%s", type(exc).__name__)
+            trace = [
+                AgentTraceStep(
+                    step=1,
+                    layer="Noema Agent",
+                    phase="runtime",
+                    status="not_achieved",
+                    title="Real orchestrator unavailable",
+                    detail=(
+                        "The GUI attempted to use the production agent orchestrator, "
+                        f"but the backend could not complete the turn: {type(exc).__name__}."
+                    ),
+                    policy="The GUI must fail closed when the real agent cannot run.",
+                    evidence="orchestrator_integration_attempted=true",
+                    databricks_target="bronze.agent_events",
+                )
+            ]
+            final_msg = "No pude completar el turno con el orquestador real. Me abstengo de dar una decisión bancaria y puedo derivarte con un asesor."
+            prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
+System Information: "{final_msg}"
+Customer Message: "{request.message}"
+IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
+"""
+            draft = _generate_with_llm(prompt)
+            if draft:
+                final_msg = draft
+
+            response = ChatResponse(
+                response=final_msg,
+                escalate_to_human=True,
+                action_taken="orchestrator_unavailable",
+                identity_verified_demo=identity_verified_demo,
+                customer_id=effective_customer_id,
+                display_name=display_name if identity_verified_demo else None,
+                segment=segment if identity_verified_demo else None,
+                trace=trace,
+            )
+            _write_chat_log(
+                request,
+                response,
+                core_action=core_result["action"],
+                model_escalated=escalate,
+            )
+            return response
+
+    if final_escalation:
+        final_msg = "I am transferring you to a human expert who can better assist you right away."
+        prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
+System Information: "{final_msg}"
+Customer Message: "{request.message}"
+IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
+"""
+        draft = _generate_with_llm(prompt)
+        if draft:
+            final_msg = draft
+
+        response = ChatResponse(
+            response=final_msg,
             escalate_to_human=True,
             action_taken="escalation",
+            identity_verified_demo=identity_verified_demo,
+            customer_id=effective_customer_id,
+            display_name=display_name if identity_verified_demo else None,
+            segment=segment if identity_verified_demo else None,
+            trace=trace,
+        )
+        _write_chat_log(
+            request,
+            response,
+            core_action=core_result["action"],
+            model_escalated=escalate,
         )
+        return response

-    return ChatResponse(
-        response=core_result["msg"], escalate_to_human=False, action_taken=core_result["action"]
+    final_msg = core_result["msg"]
+    prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
+System Information: "{final_msg}"
+Customer Message: "{request.message}"
+IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
+"""
+    draft = _generate_with_llm(prompt)
+    if draft:
+        final_msg = draft
+
+    response = ChatResponse(
+        response=final_msg,
+        escalate_to_human=False,
+        action_taken=core_result["action"],
+        identity_verified_demo=identity_verified_demo,
+        customer_id=effective_customer_id,
+        display_name=display_name if identity_verified_demo else None,
+        segment=segment if identity_verified_demo else None,
+        trace=trace,
+    )
+    _write_chat_log(
+        request,
+        response,
+        core_action=core_result["action"],
+        model_escalated=escalate,
     )
+    return response


 @app.get("/health")
 def health():
     return {"status": "ok"}
+
+
+@app.get("/api/customer-profile/{customer_id}", response_model=CustomerProfileResponse)
+def customer_profile(customer_id: str):
+    customer = get_customer_data(customer_id)
+    if not customer:
+        return CustomerProfileResponse(customer_id=customer_id, found=False)
+    display_name = _display_name(customer)
+    return CustomerProfileResponse(
+        customer_id=customer_id,
+        found=True,
+        display_name=display_name,
+        segment=customer.get("segment"),
+        identity_hint=f"my name is {display_name}",
+    )
+
+
+@app.get("/api/policy-diagnostics", response_model=PolicyDiagnosticsResponse)
+def policy_diagnostics():
+    return _policy_diagnostic_checks()


# --- CHUNK ---
Created At: 2026-10-02T23:34:21-06:00
Completed At: 2026-10-02T23:34:21-06:00

The command exited with code 0.
Output:
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


# --- CHUNK ---
Created At: 2026-10-02T23:36:02-06:00
Completed At: 2026-10-02T23:36:02-06:00

The command exited with code 0.
Output:
1235:async def chat_endpoint(request: ChatRequest):
1236-    core_result = noema_core.process(
1237-        request.message,
1238-        request.history,
1239-        request.customer_id,
1240-        request.identity_verified_demo,
1241-    )
1242-
1243-    escalate = False
1244-    if escalation_model and core_result["action"] != "escalate":
1245-        df = pd.DataFrame(
1246-            [
1247-                {
1248-                    "channel": request.channel,
1249-                    "interaction_type": request.interaction_type,
1250-                    "reason_category": request.reason_category,
1251-                }
1252-            ]
1253-        )
1254-        prob = escalation_model.predict_proba(df)[0][1]
1255-        if prob > 0.5:
1256-            escalate = True
1257-
1258-    final_escalation = core_result["action"] == "escalate" or escalate
1259-    trace = _chat_trace(request, core_result, escalate, final_escalation)
1260-    if core_result.get("identity_match") is False:
1261-        identity_verified_demo = False
1262-    else:
1263-        identity_verified_demo = bool(
1264-            request.identity_verified_demo or core_result.get("identity_verified_demo", False)
1265-        )
1266-    effective_customer_id = core_result.get("verified_customer_id") or request.customer_id
1267-    customer = get_customer_data(effective_customer_id) if effective_customer_id else {}
1268-    display_name = core_result.get("verified_display_name") or _display_name(customer) or None
1269-    segment = core_result.get("verified_segment") or customer.get("segment")
1270-
1271-    orchestrated_intent = _orchestrator_intent(noema_core.scm.evaluate(request.message)["intent"])
1272-    should_orchestrate = bool(orchestrated_intent) or core_result["action"] == "escalate"
1273-    if should_orchestrate:
1274-        try:
1275-            turn, agent_response = _run_orchestrator_turn(
1276-                request,
1277-                effective_customer_id=effective_customer_id,
1278-                runtime_intent=noema_core.scm.evaluate(request.message)["intent"],
1279-                force_human=core_result["action"] == "escalate",
1280-            )
1281-            trace = _trace_from_turn(turn)
1282-            action_taken = (
1283-                "escalation"
1284-                if turn.desenlace is Desenlace.ESCALADO
1285-                else "real_orchestrator"


# --- CHUNK ---
Created At: 2026-10-02T23:40:29-06:00
Completed At: 2026-10-02T23:40:29-06:00

The command exited with code 0.
Output:
1235:async def chat_endpoint(request: ChatRequest):
1236-    core_result = noema_core.process(
1237-        request.message,
1238-        request.history,
1239-        request.customer_id,
1240-        request.identity_verified_demo,
1241-    )
1242-
1243-    escalate = False
1244-    if escalation_model and core_result["action"] != "escalate":
1245-        df = pd.DataFrame(
1246-            [
1247-                {
1248-                    "channel": request.channel,
1249-                    "interaction_type": request.interaction_type,
1250-                    "reason_category": request.reason_category,
1251-                }
1252-            ]
1253-        )
1254-        prob = escalation_model.predict_proba(df)[0][1]
1255-        if prob > 0.5:
1256-            escalate = True
1257-
1258-    final_escalation = core_result["action"] == "escalate" or escalate
1259-    trace = _chat_trace(request, core_result, escalate, final_escalation)
1260-    if core_result.get("identity_match") is False:
1261-        identity_verified_demo = False
1262-    else:
1263-        identity_verified_demo = bool(
1264-            request.identity_verified_demo or core_result.get("identity_verified_demo", False)
1265-        )
1266-    effective_customer_id = core_result.get("verified_customer_id") or request.customer_id
1267-    customer = get_customer_data(effective_customer_id) if effective_customer_id else {}
1268-    display_name = core_result.get("verified_display_name") or _display_name(customer) or None
1269-    segment = core_result.get("verified_segment") or customer.get("segment")
1270-
1271-    orchestrated_intent = _orchestrator_intent(noema_core.scm.evaluate(request.message)["intent"])
1272-    should_orchestrate = bool(orchestrated_intent) or core_result["action"] == "escalate"
1273-    if should_orchestrate:
1274-        try:
1275-            turn, agent_response = _run_orchestrator_turn(
1276-                request,
1277-                effective_customer_id=effective_customer_id,
1278-                runtime_intent=noema_core.scm.evaluate(request.message)["intent"],
1279-                force_human=core_result["action"] == "escalate",
1280-            )
1281-            trace = _trace_from_turn(turn)
1282-            action_taken = (
1283-                "escalation"
1284-                if turn.desenlace is Desenlace.ESCALADO
1285-                else "real_orchestrator"
1286-            )
1287-            response = ChatResponse(
1288-                response=agent_response,
1289-                escalate_to_human=turn.desenlace is Desenlace.ESCALADO,
1290-                action_taken=action_taken,
1291-                identity_verified_demo=identity_verified_demo,
1292-                customer_id=effective_customer_id,
1293-                display_name=display_name if identity_verified_demo else None,
1294-                segment=segment if identity_verified_demo else None,
1295-                trace=trace,
1296-            )
1297-            _write_chat_log(
1298-                request,
1299-                response,
1300-                core_action=core_result["action"],
1301-                model_escalated=escalate,
1302-            )
1303-            return response
1304-        except Exception as exc:
1305-            LOGGER.exception("real_orchestrator_failed type=%s", type(exc).__name__)
1306-            trace = [
1307-                AgentTraceStep(
1308-                    step=1,
1309-                    layer="Noema Agent",
1310-                    phase="runtime",
1311-                    status="not_achieved",
1312-                    title="Real orchestrator unavailable",
1313-                    detail=(
1314-                        "The GUI attempted to use the production agent orchestrator, "
1315-                        f"but the backend could not complete the turn: {type(exc).__name__}."
1316-                    ),
1317-                    policy="The GUI must fail closed when the real agent cannot run.",
1318-                    evidence="orchestrator_integration_attempted=true",
1319-                    databricks_target="bronze.agent_events",
1320-                )
1321-            ]
1322-            final_msg = "No pude completar el turno con el orquestador real. Me abstengo de dar una decisión bancaria y puedo derivarte con un asesor."
1323-            prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
1324-System Information: "{final_msg}"
1325-Customer Message: "{request.message}"
1326-IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
1327-"""
1328-            draft = _generate_with_llm(prompt)
1329-            if draft:
1330-                final_msg = draft
1331-
1332-            response = ChatResponse(
1333-                response=final_msg,
1334-                escalate_to_human=True,
1335-                action_taken="orchestrator_unavailable",
1336-                identity_verified_demo=identity_verified_demo,
1337-                customer_id=effective_customer_id,
1338-                display_name=display_name if identity_verified_demo else None,
1339-                segment=segment if identity_verified_demo else None,
1340-                trace=trace,
1341-            )
1342-            _write_chat_log(
1343-                request,
1344-                response,
1345-                core_action=core_result["action"],
1346-                model_escalated=escalate,
1347-            )
1348-            return response
1349-
1350-    if final_escalation:
1351-        final_msg = "I am transferring you to a human expert who can better assist you right away."
1352-        prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
1353-System Information: "{final_msg}"
1354-Customer Message: "{request.message}"
1355-IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
1356-"""
1357-        draft = _generate_with_llm(prompt)
1358-        if draft:
1359-            final_msg = draft
1360-
1361-        response = ChatResponse(
1362-            response=final_msg,
1363-            escalate_to_human=True,
1364-            action_taken="escalation",
1365-            identity_verified_demo=identity_verified_demo,
1366-            customer_id=effective_customer_id,
1367-            display_name=display_name if identity_verified_demo else None,
1368-            segment=segment if identity_verified_demo else None,
1369-            trace=trace,
1370-        )
1371-        _write_chat_log(
1372-            request,
1373-            response,
1374-            core_action=core_result["action"],
1375-            model_escalated=escalate,
1376-        )
1377-        return response
1378-
1379-    final_msg = core_result["msg"]
1380-    prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
1381-System Information: "{final_msg}"
1382-Customer Message: "{request.message}"
1383-IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information.
1384-"""
1385-    draft = _generate_with_llm(prompt)
