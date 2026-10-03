"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Message = {
  role: "assistant" | "user";
  content: string;
};

type DiagnosticCheck = {
  name: string;
  passed: boolean;
  expected: string;
  observed: string;
};

type PolicyDiagnostics = {
  status: "pass" | "fail";
  policy_version: number;
  checks: DiagnosticCheck[];
};

type TraceStatus = "achieved" | "not_achieved" | "pending";

type AgentTraceStep = {
  step: number;
  layer: string;
  phase: string;
  status: TraceStatus;
  title: string;
  detail: string;
  policy: string;
  evidence: string;
  databricks_target: string;
};

type ChatApiResponse = {
  response?: string;
  action_taken?: string | null;
  identity_verified_demo?: boolean;
  customer_id?: string | null;
  display_name?: string | null;
  segment?: string | null;
  session_token?: string | null;
  trace?: AgentTraceStep[];
};

type CustomerProfile = {
  customer_id: string;
  found: boolean;
  display_name?: string | null;
  segment?: string | null;
  identity_hint?: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const identityPrompt =
  "Before I show account information, please tell me who you are. For this demo, type: my name is <your full name>.";

const baselineSteps: AgentTraceStep[] = [
  {
    step: 1,
    layer: "Runtime",
    phase: "runtime",
    status: "achieved",
    title: "Backend API configured",
    detail: "The chatbot is connected to the configured FastAPI backend.",
    policy: "All agent actions must pass through the backend, not the browser.",
    evidence: `api_base=${API_BASE}`,
    databricks_target: "bronze.agent_events",
  },
  {
    step: 2,
    layer: "Policy",
    phase: "policy",
    status: "achieved",
    title: "Deterministic policy engine available",
    detail: "Credit eligibility checks come from versioned policy logic.",
    policy: "The LLM may explain policy but must not decide eligibility.",
    evidence: "agent/policies/eligibility_v1.yaml",
    databricks_target: "gold.policy_diagnostics",
  },
  {
    step: 3,
    layer: "Observability",
    phase: "databricks",
    status: "pending",
    title: "Cloud write remains opt-in",
    detail: "Databricks upload planning is available, but execution requires credentials.",
    policy: "No cloud write without explicit credentials and execute mode.",
    evidence: "dry_run_supported=true",
    databricks_target: "/Volumes/noema/bronze/raw",
  },
];

const statusCopy: Record<TraceStatus, string> = {
  achieved: "Achieved",
  not_achieved: "Not achieved",
  pending: "Pending",
};

const statusClasses: Record<TraceStatus, string> = {
  achieved: "border-emerald-200 bg-emerald-50 text-emerald-800",
  not_achieved: "border-rose-200 bg-rose-50 text-rose-800",
  pending: "border-amber-200 bg-amber-50 text-amber-800",
};

export default function Home() {
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [diagnostics, setDiagnostics] = useState<PolicyDiagnostics | null>(null);
  const [diagnosticError, setDiagnosticError] = useState("");
  const [identityVerified, setIdentityVerified] = useState(false);
  const [sessionToken, setSessionToken] = useState("");
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [activeCustomerId, setActiveCustomerId] = useState("");
  const [traceSteps, setTraceSteps] = useState<AgentTraceStep[]>(baselineSteps);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: identityPrompt,
    },
  ]);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const validationSummary = useMemo(() => {
    const achieved = traceSteps.filter((step) => step.status === "achieved").length;
    const notAchieved = traceSteps.filter((step) => step.status === "not_achieved").length;
    const pending = traceSteps.filter((step) => step.status === "pending").length;
    return { achieved, notAchieved, pending };
  }, [traceSteps]);

  const handleSend = async () => {
    if (!input.trim() || isSending) return;
    const userMsg: Message = { role: "user", content: input.trim() };
    const currentMessages = [...messages, userMsg];
    setMessages(currentMessages);
    setInput("");
    setIsSending(true);
    setTraceSteps((previous) => [
      {
        step: 0,
        layer: "Request",
        phase: "request",
        status: "pending",
        title: "AI request in progress",
        detail: "The backend is routing intent, applying safeguards, and preparing a response.",
        policy: "Every assistant response must produce an auditable trace.",
        evidence: `message_length=${userMsg.content.length}`,
        databricks_target: "bronze.agent_events",
      },
      ...previous,
    ]);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          customer_id: activeCustomerId,
          session_token: sessionToken || null,
          message: userMsg.content,
          history: currentMessages
            .slice(-12)
            .map((m) => `${m.role}: ${m.content}`)
            .join("\n"),
        }),
      });
      const data: ChatApiResponse = await response.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response ?? "No response received." },
      ]);
      const verified = Boolean(data.identity_verified_demo);
      setIdentityVerified(verified);
      if (data.session_token) {
        setSessionToken(data.session_token);
      }
      if (verified && data.customer_id) {
        setActiveCustomerId(data.customer_id);
        setProfile({
          customer_id: data.customer_id,
          found: true,
          display_name: data.display_name,
          segment: data.segment,
        });
      }
      setTraceSteps(data.trace?.length ? data.trace : baselineSteps);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error connecting to AI backend." },
      ]);
      setTraceSteps([
        {
          step: 0,
          layer: "Runtime",
          phase: "runtime",
          status: "not_achieved",
          title: "Backend response not received",
          detail: "The browser could not connect to the local API.",
          policy: "Agent behavior cannot be validated without a backend trace.",
          evidence: "api_connection=false",
          databricks_target: "bronze.agent_events",
        },
        ...baselineSteps,
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const runPolicyDiagnostics = async () => {
    setIsChecking(true);
    setDiagnosticError("");
    try {
      const response = await fetch(`${API_BASE}/api/policy-diagnostics`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: PolicyDiagnostics = await response.json();
      setDiagnostics(data);
      setTraceSteps((previous) => [
        {
          step: 0,
          layer: "Policy",
          phase: "policy",
          status: data.status === "pass" ? "achieved" : "not_achieved",
          title: "Manual policy diagnostics completed",
          detail: `${data.checks.filter((check) => check.passed).length} of ${
            data.checks.length
          } deterministic policy checks passed.`,
          policy: "Eligibility must be reproducible and independent from the LLM.",
          evidence: `policy_version=${data.policy_version}; status=${data.status}`,
          databricks_target: "gold.policy_diagnostics",
        },
        ...previous,
      ]);
    } catch {
      setDiagnosticError("Could not run policy diagnostics. Check the configured API URL.");
      setDiagnostics(null);
    } finally {
      setIsChecking(false);
    }
  };

  const startIdentityVerification = () => {
    setInput("my name is ");
    inputRef.current?.focus();
  };

  const resetIdentity = () => {
    setIdentityVerified(false);
    setActiveCustomerId("");
    setProfile(null);
    setInput("");
    setMessages([
      {
        role: "assistant",
        content: identityPrompt,
      },
    ]);
    setTraceSteps(baselineSteps);
    inputRef.current?.focus();
  };

  return (
    <main className="min-h-screen bg-slate-100 px-6 py-8 text-slate-950">
      <div className="mx-auto grid w-full max-w-7xl gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(420px,0.95fr)]">
        <section className="flex min-h-[720px] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-950 px-5 py-4 text-white">
            <div>
              <h1 className="text-lg font-semibold">Noema AI Assistant</h1>
              <p className="text-sm text-slate-300">
                Demo profile:{" "}
                {identityVerified
                  ? `${profile?.display_name ?? "Verified customer"} · ${activeCustomerId}${
                      profile?.segment ? ` · ${profile.segment}` : ""
                    }`
                  : "Identity not verified"}
              </p>
            </div>
            <button
              onClick={identityVerified ? resetIdentity : startIdentityVerification}
              className={`rounded px-2 py-1 text-xs font-semibold ${
                identityVerified
                  ? "bg-slate-200 text-slate-950 hover:bg-slate-300"
                  : "bg-emerald-500 text-emerald-950 hover:bg-emerald-400"
              }`}
            >
              {identityVerified ? "Reset identity" : "Verify identity"}
            </button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`max-w-[82%] rounded-lg px-4 py-3 text-sm leading-6 ${
                  message.role === "user"
                    ? "ml-auto bg-blue-600 text-white"
                    : "mr-auto bg-slate-100 text-slate-950"
                }`}
              >
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">
                  {message.role === "user" ? "You" : "Noema"}
                </div>
                {message.content}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="flex gap-3 border-t border-slate-200 bg-slate-50 p-4">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void handleSend();
                }
              }}
              placeholder="Type a banking question..."
              className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
            <button
              onClick={() => void handleSend()}
              disabled={isSending}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {isSending ? "Sending" : "Send"}
            </button>
          </div>
        </section>

        <aside className="flex max-h-[720px] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">Step-by-Step Agent Logic</h2>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  Procedure, policies, rules, guardrails, evidence, and Databricks targets.
                </p>
              </div>
              <button
                onClick={() => void runPolicyDiagnostics()}
                disabled={isChecking}
                className="rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {isChecking ? "Checking" : "Run"}
              </button>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs font-semibold">
              <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-2 text-emerald-800">
                {validationSummary.achieved} Achieved
              </div>
              <div className="rounded-md border border-rose-200 bg-rose-50 px-2 py-2 text-rose-800">
                {validationSummary.notAchieved} Not achieved
              </div>
              <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-2 text-amber-800">
                {validationSummary.pending} Pending
              </div>
            </div>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {traceSteps.map((step, index) => (
              <article
                key={`${step.phase}-${step.title}-${index}`}
                className="rounded-md border border-slate-200 bg-white"
              >
                <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-3 py-3">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Step {step.step || index + 1} · {step.layer} · {step.phase}
                    </div>
                    <h3 className="mt-1 text-sm font-semibold text-slate-950">{step.title}</h3>
                  </div>
                  <span
                    className={`shrink-0 rounded border px-2 py-1 text-xs font-semibold ${
                      statusClasses[step.status]
                    }`}
                  >
                    {statusCopy[step.status]}
                  </span>
                </div>
                <ul className="space-y-2 px-3 py-3 text-sm leading-6 text-slate-700">
                  <li>
                    <span className="font-semibold text-slate-950">Rule:</span> {step.policy}
                  </li>
                  <li>
                    <span className="font-semibold text-slate-950">Observed:</span>{" "}
                    {step.detail}
                  </li>
                  <li>
                    <span className="font-semibold text-slate-950">Evidence:</span>{" "}
                    {step.evidence}
                  </li>
                  <li>
                    <span className="font-semibold text-slate-950">Databricks:</span>{" "}
                    {step.databricks_target}
                  </li>
                </ul>
              </article>
            ))}

            <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-950">Policy Diagnostics</h3>
                  <p className="mt-1 text-sm text-slate-600">
                    Deterministic checks from the backend policy engine.
                  </p>
                </div>
                {diagnostics && (
                  <span
                    className={`rounded border px-2 py-1 text-xs font-semibold ${
                      diagnostics.status === "pass"
                        ? statusClasses.achieved
                        : statusClasses.not_achieved
                    }`}
                  >
                    {diagnostics.status.toUpperCase()}
                  </span>
                )}
              </div>

              {diagnosticError && (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {diagnosticError}
                </div>
              )}

              {!diagnostics && !diagnosticError && (
                <div className="rounded-md border border-dashed border-slate-300 bg-white px-3 py-6 text-center text-sm text-slate-600">
                  Run diagnostics to load the detailed policy checks.
                </div>
              )}

              {diagnostics && (
                <div className="space-y-3">
                  <div className="text-sm text-slate-600">
                    Policy version {diagnostics.policy_version}
                  </div>
                  {diagnostics.checks.map((check) => (
                    <div key={check.name} className="rounded-md border border-slate-200 bg-white p-3">
                      <div className="mb-2 flex items-center gap-2">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            check.passed ? "bg-emerald-500" : "bg-red-500"
                          }`}
                        />
                        <h4 className="text-sm font-semibold">{check.name}</h4>
                      </div>
                      <ul className="space-y-1 text-sm text-slate-700">
                        <li>
                          <span className="font-semibold text-slate-950">Expected:</span>{" "}
                          {check.expected}
                        </li>
                        <li>
                          <span className="font-semibold text-slate-950">Observed:</span>{" "}
                          {check.observed}
                        </li>
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </aside>
      </div>
    </main>
  );
}
