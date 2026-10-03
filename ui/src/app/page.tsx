"use client";
import { useState, useRef, useEffect } from "react";

export default function Home() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "assistant", content: "Hello! I'm Noema, your AI Banking Agent. How can I help you with your financial needs today?" }
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input) return;
    const userMsg = { role: "user", content: input };
    const currentMessages = [...messages, userMsg];
    setMessages(currentMessages);
    setInput("");

    try {
      const response = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          customer_id: "CLI-VFJVE80MLIC5",
          message: input,
          history: currentMessages.map(m => `${m.role}: ${m.content}`).join("\n")
        }),
      });
      const data = await response.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: "Error connecting to AI backend." }]);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-gray-50 text-gray-900 font-sans p-8 items-center justify-center">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl overflow-hidden flex flex-col h-[600px]">
        <div className="bg-blue-600 p-4 text-white font-bold text-xl flex justify-between items-center">
          <span>Noema AI Assistant</span>
          <span className="text-sm font-normal bg-blue-700 px-2 py-1 rounded">Beta</span>
        </div>

        <div className="flex-1 p-4 overflow-y-auto flex flex-col gap-4">
          {messages.map((m, i) => (
            <div key={i} className={`p-3 rounded-lg max-w-[80%] ${m.role === 'user' ? 'bg-blue-100 self-end' : 'bg-gray-100 self-start'}`}>
              <span className="font-semibold">{m.role === 'user' ? 'You' : 'Noema'}:</span> {m.content}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 bg-gray-100 border-t flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type your message or use voice..."
            className="flex-1 p-2 rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button onClick={handleSend} className="bg-blue-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-blue-700">
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
