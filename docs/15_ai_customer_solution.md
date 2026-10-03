# AI-First Customer Solution: Voice & Chatbot System

## Architecture Overview

The new AI-first solution leverages our deep learning models alongside the **Semantic Cognition Matrix (SCM)** and **Noema Core** to provide a highly capable, autonomous banking expert.

### 1. The Core AI Agent (LLaMA & Noema Core)
- **Local Free-Tier LLM**: We use a LLaMA-based model to generate precise, bank-specialized responses without incurring API costs.
- **Semantic Cognition Matrix (SCM)**: Extracts intents, entities (e.g., account numbers, balances), and sentiment from customer inputs.
- **Neural Symbolic Logic**: Combines the LLM's generative flexibility with deterministic business rules, ensuring that sensitive transactions or regulatory boundaries are strictly adhered to.

### 2. Machine Learning Integration
- **Support Escalation Model**: Continuously evaluates the interaction (`support_escalation.joblib`). If the probability of requiring a human exceeds a threshold, the system automatically transfers the user to a real agent.
- **Deep Interest Model**: Informs the LLM of the customer's propensity for certain products, allowing proactive assistance.
- **New Segmentation Model**: Classifies users to tailor the tone, language, and offers specifically for VIP or standard customers.

### 3. Frontend & Backend
- **Backend (FastAPI)**: Serves the `/api/chat` endpoint, integrating duckdb queries, ML inference, and the Noema Core.
- **Frontend (Next.js & React)**: A Voice-First UI with fallback to text chat. It interacts directly with the API to render real-time responses.

## Future Steps
- Deploy LLaMA via `llama-cpp-python` or `Ollama` on the server.
- Refine the SCM rules to handle voice-to-text transcriptions accurately.
