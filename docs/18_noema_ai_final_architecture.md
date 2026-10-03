# Noema Bank Agent: Final AI Architecture

## Overview
The Noema Bank Agent represents the capstone of our hackathon submission: a highly intelligent, grounded, and safe AI-first banking solution. It replaces traditional deterministic chatbots with a dynamic **Neural Symbolic AI** (The Noema Core).

## 1. The Semantic Cognition Matrix (SCM)
To ensure the bank does not blindly trust a generative LLM with sensitive financial actions, all incoming user queries pass through the **Semantic Cognition Matrix**.
- **Intent Routing:** Evaluates whether a query is related to balance inquiries, product requests, or requires human escalation.
- **LLM Bypass:** For highly sensitive intents (like Escalation), the SCM completely bypasses the LLM to guarantee a safe, strict, and compliant response, effectively wrapping the generative AI in deterministic rules.

## 2. Machine Learning Integration
Instead of relying on the LLM to guess what a customer wants, we plugged in our predictive Machine Learning models directly into the routing layer:
- **Support Escalation Model:** A Random Forest that predicts if an interaction is highly likely to lead to customer frustration. If the probability exceeds 50%, the AI safely intercepts the chat and transfers the user to a human.
- **Deep Interest Model:** For product recommendations, the AI consults our trained ML pipelines to offer data-backed products (like the Factored Premium Card) rather than hallucinating generic offers.

## 3. Database Grounding (Zero Hallucination)
A key achievement of the architecture is strict factual grounding.
When a user authenticates, the backend dynamically connects to the `data/noema.duckdb` instance (read-only) and extracts the user's exact profile from the `noema_gold.customer_360` table (First Name, Segment, Total Balance, Income, etc.).
This data is injected into the LLM's system prompt context. If the user asks "What is my balance?", the AI responds using the absolute truth from the database, eliminating the risk of LLM hallucination.

## 4. Technology Stack
- **Frontend:** React / Next.js 15 (Responsive, memory-context-aware chat UI).
- **Backend API:** FastAPI (Python), handling CORS, orchestration, ML inference loading, and DuckDB querying.
- **LLM Engine:** Google Gemini 3.5 Flash-Lite via the `google-genai` SDK / raw HTTP requests, optimized for low latency and high volume.
- **Data Layer:** Medallion architecture using DuckDB.

## 5. Security & Rate Limiting
- To protect against rate limits and API timeouts, the backend implements exponential backoff and a 20-second timeout on LLM API calls.
- The system is completely resilient to network failures. If the LLM is down, the SCM still answers basic queries and processes ML model escalations.
